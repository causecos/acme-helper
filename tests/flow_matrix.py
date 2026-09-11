#!/usr/bin/env python3
import os
import pathlib
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACME = str(ROOT / 'acme')
CORE = str(ROOT / 'acme_cli.py')
MOCK = str(ROOT / 'tests' / 'mock-acme.sh')
VERSION = '1.11.0'
MAIN_PROMPT = 'Action (number or command)'


class T:
    def __init__(self):
        self.n = 0
        self.fail = []
        self.groups = {}

    def ok(self, group, cond, msg):
        self.n += 1
        self.groups[group] = self.groups.get(group, 0) + 1
        if cond:
            print('PASS {} - {}'.format(group, msg))
        else:
            self.fail.append((group, msg))
            print('FAIL {} - {}'.format(group, msg))

    def done(self):
        if self.fail:
            print('SUMMARY FAIL {}/{}'.format(self.n - len(self.fail), self.n))
            for group, msg in self.fail:
                print('  - {}: {}'.format(group, msg))
            return 1
        print('SUMMARY PASS {}/{}'.format(self.n, self.n))
        for group in sorted(self.groups):
            print('GROUP {} {}'.format(group, self.groups[group]))
        return 0


def run_cli(args, env=None, data=None):
    merged = os.environ.copy()
    merged.update(env or {})
    merged.setdefault("ACME_HELPER_LANG", "en")
    return subprocess.run([ACME] + args, input=data, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged, timeout=20)


def argvlog(path):
    p = pathlib.Path(path)
    return p.read_text().splitlines() if p.exists() else []


def clear(path):
    try:
        pathlib.Path(path).unlink()
    except FileNotFoundError:
        pass


def make_mock(td, body, name):
    path = pathlib.Path(td) / name
    path.write_text('#!/usr/bin/env bash\nset -u\n' + body)
    os.chmod(str(path), 0o755)
    return str(path)


def parse_mock_catalog():
    text = subprocess.check_output([MOCK, '--help'], text=True)
    commands = []
    params = []
    mode = None
    for raw in text.splitlines():
        if raw.startswith('Commands:'):
            mode = 'commands'
            continue
        if raw.startswith('Parameters:'):
            mode = 'params'
            continue
        if not re.match(r'^\s+-', raw):
            continue
        trimmed = raw.lstrip()
        spec = re.split(r'\s{2,}', trimmed, maxsplit=1)[0]
        long_opt = re.search(r'--[A-Za-z0-9-]+', spec)
        option = long_opt.group(0) if long_opt else re.split(r'[\s,]', spec, maxsplit=1)[0]
        if mode == 'commands':
            commands.append(option)
        elif mode == 'params':
            params.append(option)
    completion = ROOT / 'tests' / 'acme.sh.completion'
    if completion.exists():
        text = completion.read_text()
        m = re.search(r'if \[ "\$COMP_CWORD" -eq 1 \]; then.*?_acme_sh_add_matches "(.*?)"', text, re.S)
        if m:
            for option in re.findall(r'--[A-Za-z0-9-]+', m.group(1)):
                if option not in commands:
                    commands.append(option)
    return commands, params


COMMANDS, PARAMS = parse_mock_catalog()


def idx(items, option):
    return str(items.index(option) + 1)


class PtyRun:
    """Real controlling-TTY harness. pty.fork makes Ctrl-C/Ctrl-D terminal semantics real."""
    def __init__(self, args, env):
        merged = os.environ.copy()
        merged.update(env)
        merged.setdefault("ACME_HELPER_LANG", "en")
        pid, master = pty.fork()
        if pid == 0:
            os.execve(ACME, [ACME] + args, merged)
        self.pid = pid
        self.master = master
        self.buf = b''
        self.cursor = 0
        self.status = None

    def _pump(self, timeout=0.2):
        r, _, _ = select.select([self.master], [], [], timeout)
        if not r:
            return False
        try:
            chunk = os.read(self.master, 4096)
        except OSError:
            return False
        if not chunk:
            return False
        self.buf += chunk
        return True

    def expect(self, text, timeout=3):
        target = text.encode('utf-8')
        end = time.time() + timeout
        found = self.buf.find(target, self.cursor)
        while found < 0 and time.time() < end:
            self._pump(min(0.2, max(0.01, end - time.time())))
            found = self.buf.find(target, self.cursor)
            if self._poll() is not None and found < 0:
                self._pump(0.05)
                found = self.buf.find(target, self.cursor)
                break
        if found < 0:
            raise AssertionError('timeout/missing {!r}; got {!r}'.format(text, self.buf[-3000:]))
        self.cursor = found + len(target)
        return self

    def send(self, text):
        os.write(self.master, text.encode('utf-8'))
        return self

    def line(self, text=''):
        return self.send(text + '\n')

    def ctrl_c(self):
        time.sleep(0.08)
        return self.send('\x03')

    def ctrl_d(self):
        time.sleep(0.08)
        return self.send('\x04')

    def _poll(self):
        if self.status is not None:
            return self.status
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return self.status
        if pid == self.pid:
            self.status = status
            return status
        return None

    def finish(self, timeout=6):
        end = time.time() + timeout
        while self._poll() is None and time.time() < end:
            self._pump(0.05)
        if self._poll() is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, self.status = os.waitpid(self.pid, 0)
        for _ in range(10):
            if not self._pump(0.02):
                break
        try:
            os.close(self.master)
        except OSError:
            pass
        if os.WIFEXITED(self.status):
            rc = os.WEXITSTATUS(self.status)
        elif os.WIFSIGNALED(self.status):
            rc = 128 + os.WTERMSIG(self.status)
        else:
            rc = 255
        return rc, self.buf.decode('utf-8', 'replace')

    def abort(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass
        try:
            os.close(self.master)
        except OSError:
            pass


def pty_case(t, group, label, args, env, driver, assertion):
    s = PtyRun(args, env)
    try:
        driver(s)
        if not args and group != 'pty-signals':
            # Main now returns to its task menu. Explicitly exercise that transition and exit.
            s.expect(MAIN_PROMPT).line('0')
        rc, text = s.finish()
        t.ok(group, assertion(rc, text), label + (" [rc={}, output={!r}]".format(rc, text[-700:]) if not assertion(rc, text) else ""))
    except Exception as exc:
        s.abort()
        t.ok(group, False, '{}: {}'.format(label, exc))


def main():
    t = T()
    td = tempfile.mkdtemp(prefix='acme-flow-v170-')
    system_core = pathlib.Path('/usr/local/lib/acme/acme_cli.py')
    system_dir = system_core.parent
    system_created = False
    try:
        runtime_home = pathlib.Path(td) / 'runtime-acme'
        runtime_home.mkdir()
        runtime_mock = runtime_home / 'acme.sh'
        shutil.copy2(MOCK, str(runtime_mock))
        os.chmod(str(runtime_mock), 0o755)
        shutil.copytree(str(ROOT / 'tests' / 'dnsapi'), str(runtime_home / 'dnsapi'))
        shutil.copytree(str(ROOT / 'tests' / 'deploy'), str(runtime_home / 'deploy'))
        shutil.copytree(str(ROOT / 'tests' / 'notify'), str(runtime_home / 'notify'))
        shutil.copy2(str(ROOT / 'tests' / 'acme.sh.completion'), str(runtime_home / 'acme.sh.completion'))
        log = td + '/argv'
        out = td + '/out'
        account = td + '/account.conf'
        wrapper = td + '/wrapper.ini'
        env = {
            'ACME_SH_BIN': str(runtime_mock),
            'ACME_VERSION_BACKUP_DIR': td + '/version-backups',
            'MOCK_HISTORY': td + '/history',
            'MOCK_LOG': log,
            'ACME_OUTPUT_ROOT': out,
            'ACME_ACCOUNT_CONF': account,
            'ACME_WRAPPER_CONFIG': wrapper,
        }

        cert_list = pathlib.Path(td) / 'certs.list'
        cert_list.write_text(
            'Main_Domain|KeyLength|SAN_Domains|Profile|CA|Created|Renew\n'
            '*.aa.test|"ec-256"|*.bb.test,*.cc.test||LetsEncrypt.org|2026-09-01T00:00:00Z|2026-10-30T00:00:00Z\n'
            'example.test|"2048"|www.example.test||LetsEncrypt.org|2026-08-01T00:00:00Z|2026-09-29T00:00:00Z\n'
        )
        cert_info_dir = pathlib.Path(td) / 'cert-info'; cert_info_dir.mkdir()
        (cert_info_dir / '_wild_.aa.test.info').write_text(
            'DOMAIN_CONF=/tmp/aa.conf\nLe_Domain=*.aa.test\nLe_Alt=*.bb.test,*.cc.test\n'
            'Le_Webroot=dns_namesilo\nLe_RealKeyPath=/etc/ssl/acme/aa/key.pem\n'
            'Le_RealFullChainPath=/etc/ssl/acme/aa/fullchain.pem\n'
        )
        (cert_info_dir / 'example.test.info').write_text(
            'DOMAIN_CONF=/tmp/example.conf\nLe_Domain=example.test\nLe_Alt=www.example.test\nLe_Webroot=dns_cf\n'
        )
        env['MOCK_CERT_LIST'] = str(cert_list)
        env['MOCK_CERT_INFO_DIR'] = str(cert_info_dir)

        cron_state = pathlib.Path(td) / 'cron.state'; cron_state.write_text('disabled\n')
        cron_bin = pathlib.Path(td) / 'cron-bin'; cron_bin.mkdir()
        crontab = cron_bin / 'crontab'
        crontab.write_text('#!/bin/sh\nif [ "${1:-}" = "-l" ]; then\n  if [ -r "$MOCK_CRON_STATE" ] && grep -q enabled "$MOCK_CRON_STATE"; then\n    echo "0 0 * * * \"$ACME_SH_BIN\" --cron --home \"$(dirname "$ACME_SH_BIN")\" > /dev/null"\n    exit 0\n  fi\n  exit 1\nfi\nexit 2\n')
        os.chmod(str(crontab), 0o755)
        cron_env = dict(env, MOCK_CRON_STATE=str(cron_state), PATH=str(cron_bin) + ':' + os.environ.get('PATH',''))

        # ----- CLI dispatcher / launcher -----
        p = run_cli(['--version'], env)
        t.ok('cli-main', p.returncode == 0 and 'v' + VERSION in p.stdout, 'version')
        p = run_cli(['version'], env)
        t.ok('cli-main', p.returncode == 0 and 'wrapper_version=' + VERSION in p.stdout and 'acme_sh_version=3.1.5' in p.stdout and 'acme_sh_compatibility=probed-compatible' in p.stdout and 'public_command_guidance=35/35' in p.stdout and 'friendly_command_routes=35/35' in p.stdout and 'public_parameter_guidance=80/80' in p.stdout, 'version support details')
        p = run_cli(['--help'], env)
        t.ok('cli-main', p.returncode == 0 and 'minimal output' in p.stderr and 'config' in p.stderr and 'COMMAND --help' in p.stderr, 'help documents minimal + config defaults')
        p = run_cli(['defaults'], env)
        t.ok('cli-main', p.returncode == 0 and 'config_file=' + wrapper in p.stdout and 'output_layout=minimal' in p.stdout, 'defaults effective values')
        for args, label in [
            (['defaults', 'x'], 'defaults rejects extra'),
            (['status', '--bad'], 'status rejects bad option'),
            (['update', 'x'], 'update rejects extra'),
            (['version', 'x'], 'version rejects extra'),
            (['config', 'dns_cf', 'SECRET'], 'config rejects argv secret'),
            (['config', 'bad'], 'config rejects bad target'),
        ]:
            p = run_cli(args, env, 'x\n')
            t.ok('cli-errors', p.returncode == 2 and ('SECRET' not in p.stderr), label)
        p = run_cli(['-config'], env)
        t.ok('ablation', p.returncode == 2, 'removed -config alias remains removed')
        p = run_cli(['--update'], env)
        t.ok('ablation', p.returncode == 2, 'removed --update alias remains removed')
        clear(log)
        p = run_cli(['raw'], env)
        t.ok('ablation', p.returncode == 0 and '-d' in argvlog(log) and 'raw' in argvlog(log), 'removed raw alias is ordinary shorthand domain, not native mode')

        # Launcher local core path is exercised by every invocation. Test fallback and error branches too.
        if not system_core.exists():
            system_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CORE, str(system_core))
            os.chmod(str(system_core), 0o755)
            system_created = True
        launcher_dir = pathlib.Path(td) / 'launcher-fallback'
        launcher_dir.mkdir()
        shutil.copy2(ACME, str(launcher_dir / 'acme'))
        os.chmod(str(launcher_dir / 'acme'), 0o755)
        p = subprocess.run([str(launcher_dir / 'acme'), '--version'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, PATH='/usr/bin:/bin'))
        t.ok('launcher', p.returncode == 0 and 'v' + VERSION in p.stdout, 'system core fallback')
        if system_created:
            system_core.unlink()
            try:
                system_dir.rmdir()
            except OSError:
                pass
            system_created = False
        p = subprocess.run(['/bin/bash', str(launcher_dir / 'acme')], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, PATH='/usr/bin:/bin'))
        t.ok('launcher', p.returncode == 1 and 'acme_cli.py not found' in p.stderr, 'missing core')
        no_python_bin = pathlib.Path(td) / 'no-python-bin'
        no_python_bin.mkdir()
        os.symlink(shutil.which('bash'), str(no_python_bin / 'bash'))
        os.symlink(shutil.which('dirname'), str(no_python_bin / 'dirname'))
        p = subprocess.run([ACME, '--version'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, PATH=str(no_python_bin)))
        t.ok('launcher', p.returncode == 1 and 'python3 is required' in p.stderr, 'missing python')
        old_python_bin = pathlib.Path(td) / 'old-python-launcher-bin'
        old_python_bin.mkdir()
        os.symlink(shutil.which('bash'), str(old_python_bin / 'bash'))
        os.symlink(shutil.which('dirname'), str(old_python_bin / 'dirname'))
        real_python = sys.executable
        fake_python = old_python_bin / 'python3'
        fake_python.write_text(('#!/bin/sh\n'
            'core="$2"\n'
            'shift 2\n'
            'exec "{}" -S -c \'import runpy,sys; core=sys.argv[1]; args=sys.argv[2:]; sys.version_info=(3,5,10); sys.argv=[core]+args; runpy.run_path(core, run_name="__main__")\' "$core" "$@"\n'
        ).format(real_python))
        os.chmod(str(fake_python), 0o755)
        p = subprocess.run([ACME, '--version'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, PATH=str(old_python_bin)))
        t.ok('launcher', p.returncode == 2 and 'Python 3.6+ is required; found 3.5' in p.stderr, 'old python rejected by core')

        # ----- Wrapper installer + acme.sh installer -----
        prefix_dir = pathlib.Path(td) / 'prefix'
        install_env = dict(os.environ, PREFIX=str(prefix_dir), HOME=str(pathlib.Path(td) / 'wrapper-home'))
        pathlib.Path(install_env['HOME']).mkdir(parents=True, exist_ok=True)
        p = subprocess.run([str(ROOT / 'install.sh')], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=install_env)
        installed_wrapper = prefix_dir / 'bin' / 'acme'
        installed_core = prefix_dir / 'lib' / 'acme' / 'acme_cli.py'
        t.ok('wrapper-install', p.returncode == 0 and installed_wrapper.exists() and installed_core.exists() and 'v' + VERSION in p.stdout, 'install.sh installs wrapper/core and prints version')

        # install.sh negative branches. Keep fake PATH minimal so missing dependencies are real.
        inst_neg = pathlib.Path(td) / 'install-neg'; inst_neg.mkdir()
        def link_cmd(folder, name, target=None):
            target = target or shutil.which(name)
            if target:
                os.symlink(target, str(folder / name))
        for case_name, setup, expected in [
            ('non-linux', 'darwin', 'Linux is the tested platform'),
            ('missing-python', 'no-python', 'python3 >= 3.6 is required'),
            ('old-python', 'old-python', 'python3 >= 3.6 is required'),
            ('missing-install', 'no-install', 'POSIX install utility is required'),
        ]:
            fb = inst_neg / case_name; fb.mkdir()
            link_cmd(fb, 'bash'); link_cmd(fb, 'dirname')
            if setup == 'darwin':
                (fb/'uname').write_text('#!/bin/sh\necho Darwin\n'); os.chmod(str(fb/'uname'),0o755)
            else:
                link_cmd(fb, 'uname')
            if setup == 'old-python':
                (fb/'python3').write_text('#!/bin/sh\nif [ "${1:-}" = "-c" ]; then exit 1; fi\necho "Python 3.5.10"\n'); os.chmod(str(fb/'python3'),0o755)
            elif setup in ('darwin','no-install'):
                link_cmd(fb, 'python3')
            if setup not in ('darwin','no-python','old-python','no-install'):
                link_cmd(fb, 'install')
            if setup != 'no-install' and setup not in ('darwin','no-python','old-python'):
                link_cmd(fb, 'install')
            neg_env = {'PATH':str(fb),'PREFIX':str(inst_neg/(case_name+'-prefix')),'HOME':str(inst_neg/(case_name+'-home'))}
            pathlib.Path(neg_env['HOME']).mkdir()
            pneg=subprocess.run([str(ROOT/'install.sh')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=neg_env)
            t.ok('wrapper-install-errors', pneg.returncode==2 and expected in pneg.stderr, case_name)

        lone = inst_neg / 'missing-payload'; lone.mkdir(); shutil.copy2(str(ROOT/'install.sh'), str(lone/'install.sh'))
        pneg=subprocess.run([str(lone/'install.sh')],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ, PREFIX=str(inst_neg/'missing-payload-prefix'), HOME=str(inst_neg/'missing-payload-home')))
        t.ok('wrapper-install-errors', pneg.returncode==2 and 'must be beside install.sh' in pneg.stderr, 'missing wrapper payload')

        p = run_cli(['install', '--email', 'ops@example.com'], env)
        t.ok('cli-install', p.returncode == 0 and 'already installed' in p.stderr, 'acme.sh already installed -> no reinstall')
        p = run_cli(['install', '--email', 'bad-email'], {'HOME': td + '/install-bad-email', 'PATH': os.environ.get('PATH','')})
        t.ok('cli-install-errors', p.returncode == 2 and 'comma-separated ASCII email addresses' in p.stderr, 'invalid email rejected before download')
        p = run_cli(['install', '--bogus'], {'HOME': td + '/install-bogus', 'PATH': os.environ.get('PATH','')})
        t.ok('cli-install-errors', p.returncode == 2 and 'unknown install option' in p.stderr, 'unknown install option rejected')
        p = run_cli(['install', '--email', 'ops@example.com;touch-x'], {'HOME': td + '/install-meta-email', 'PATH': os.environ.get('PATH','')})
        t.ok('cli-install-errors', p.returncode == 2 and 'comma-separated ASCII email addresses' in p.stderr, 'installer email rejects shell metacharacters before download')
        p = run_cli(['install', '--email', 'ops*@example.com'], {'HOME': td + '/install-glob-email', 'PATH': os.environ.get('PATH','')})
        t.ok('cli-install-errors', p.returncode == 2 and 'comma-separated ASCII email addresses' in p.stderr, 'installer email rejects glob expansion characters')
        bad_acme_path = td + '/not-executable-acme.sh'
        pathlib.Path(bad_acme_path).write_text('#!/bin/sh\nexit 0\n')
        os.chmod(bad_acme_path, 0o644)
        p = run_cli(['install', '--email', 'ops@example.com'], {'HOME': td + '/install-bad-env', 'PATH': os.environ.get('PATH',''), 'ACME_SH_BIN': bad_acme_path})
        t.ok('cli-install-errors', p.returncode == 2 and 'ACME_SH_BIN is set but not executable' in p.stderr, 'invalid ACME_SH_BIN blocks install before download')
        p = run_cli(['version'], {'HOME': td + '/version-bad-env', 'ACME_SH_BIN': bad_acme_path})
        t.ok('cli-main', p.returncode == 0 and 'acme_sh_compatibility=invalid-configured-path' in p.stdout and 'acme_sh_path=invalid-configured:' in p.stdout, 'version reports invalid configured acme.sh path')
        p = run_cli(['install', '--help'], {'HOME':td+'/install-help'})
        t.ok('cli-install-errors', p.returncode==0 and 'Usage: acme install' in p.stderr, 'install help branch')
        p = run_cli(['install', '--email'], {'HOME':td+'/install-missing-value'})
        t.ok('cli-install-errors', p.returncode==2 and 'requires a value' in p.stderr, 'install email missing value')

        fakebin = pathlib.Path(td) / 'fakebin'
        fakebin.mkdir()
        installer_body = pathlib.Path(td) / 'installer-body.sh'
        installer_body.write_text("""#!/bin/sh
set -eu
mkdir -p "$HOME/.acme.sh"
cp "$MOCK_INSTALL_SOURCE" "$HOME/.acme.sh/acme.sh"
chmod 755 "$HOME/.acme.sh/acme.sh"
cp -R "$MOCK_INSTALL_DNSAPI" "$HOME/.acme.sh/dnsapi"
case "${BRANCH:-}" in
  v[0-9]*.[0-9]*.[0-9]*|[0-9]*.[0-9]*.[0-9]*)
    v=${BRANCH#v}
    sed "s/^embedded_version=.*/embedded_version=\"$v\"/" "$HOME/.acme.sh/acme.sh" > "$HOME/.acme.sh/acme.sh.tmp"
    mv "$HOME/.acme.sh/acme.sh.tmp" "$HOME/.acme.sh/acme.sh"
    chmod 755 "$HOME/.acme.sh/acme.sh"
    ;;
esac
printf '%s\n' "$@" > "$MOCK_INSTALL_LOG"
if [ -n "${MOCK_BRANCH_LOG:-}" ]; then printf '%s\n' "${BRANCH:-}" > "$MOCK_BRANCH_LOG"; fi
""")
        fakecurl = fakebin / 'curl'
        fakecurl.write_text('#!/bin/sh\ncat "{}"\n'.format(installer_body))
        os.chmod(str(fakecurl), 0o755)
        for name, target in [('python3', shutil.which('python3')), ('bash', shutil.which('bash')), ('sh', shutil.which('sh')), ('cat', shutil.which('cat')), ('mkdir', shutil.which('mkdir')), ('chmod', shutil.which('chmod')), ('dirname', shutil.which('dirname')), ('cp', shutil.which('cp')), ('sed', shutil.which('sed')), ('mv', shutil.which('mv'))]:
            os.symlink(target, str(fakebin / name))
        install_home = pathlib.Path(td) / 'install-home'
        install_home.mkdir()
        install_log = td + '/install.args'
        install_case_env = {'HOME': str(install_home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': install_log, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        p = run_cli(['install', '--email', 'ops@example.com', '--no-cron', '--no-profile'], install_case_env)
        t.ok('cli-install', p.returncode == 0 and (install_home / '.acme.sh' / 'acme.sh').exists(), 'official installer pipeline success path')
        t.ok('cli-install', argvlog(install_log) == ['email=ops@example.com', '--no-cron', '--no-profile'], 'installer receives exact email/cron/profile argv')

        install_bare_home = pathlib.Path(td) / 'install-bare-home'; install_bare_home.mkdir()
        install_bare_log = td + '/install-bare.args'
        env_bare = {'HOME': str(install_bare_home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': install_bare_log, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        p = run_cli(['install'], env_bare)
        t.ok('cli-install', p.returncode == 0 and argvlog(install_bare_log) == ['--no-cron'], 'bare install succeeds without email and keeps cron off')

        install_no_email_home = pathlib.Path(td) / 'install-no-email-home'; install_no_email_home.mkdir()
        install_no_email_log = td + '/install-no-email.args'
        env_no_email = {'HOME': str(install_no_email_home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': install_no_email_log, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        p = run_cli(['install', '--version', '3.1.4', '--no-profile'], env_no_email)
        t.ok('cli-install', p.returncode == 0 and argvlog(install_no_email_log) == ['--no-cron', '--no-profile'], 'email optional; default install disables cron and omits empty email')
        install_cron_home = pathlib.Path(td) / 'install-cron-home'; install_cron_home.mkdir()
        install_cron_log = td + '/install-cron.args'
        env_install_cron = {'HOME': str(install_cron_home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': install_cron_log, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        p = run_cli(['install', '--version', '3.1.4', '--cron', '--no-profile'], env_install_cron)
        t.ok('cli-install', p.returncode == 0 and argvlog(install_cron_log) == ['--no-profile'], 'explicit --cron enables installer cron without email')

        # Explicit version/tag and branch install branches.
        install_v_home = pathlib.Path(td) / 'install-version-home'; install_v_home.mkdir()
        install_v_log = td + '/install-version.args'; install_v_branch = td + '/install-version.branch'
        env_v = {'HOME': str(install_v_home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': install_v_log, 'MOCK_BRANCH_LOG': install_v_branch, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        p = run_cli(['install', '--email', 'ops@example.com', '--version', '3.1.4'], env_v)
        t.ok('cli-install-version', p.returncode == 0 and pathlib.Path(install_v_branch).read_text().strip() == '3.1.4' and 'acme_sh_version=3.1.4' in run_cli(['version'], {'HOME': str(install_v_home)}).stdout, 'install explicit release tag/version')
        install_b_home = pathlib.Path(td) / 'install-branch-home'; install_b_home.mkdir()
        install_b_log = td + '/install-branch.args'; install_b_branch = td + '/install-branch.branch'
        env_b = {'HOME': str(install_b_home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': install_b_log, 'MOCK_BRANCH_LOG': install_b_branch, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        p = run_cli(['install', '--email', 'ops@example.com', '--branch', 'master'], env_b)
        t.ok('cli-install-version', p.returncode == 0 and pathlib.Path(install_b_branch).read_text().strip() == 'master', 'install explicit branch')
        install_d_home = pathlib.Path(td) / 'install-default-home'; install_d_home.mkdir()
        install_d_log = td + '/install-default.args'; install_d_branch = td + '/install-default.branch'
        env_d = {'HOME': str(install_d_home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': install_d_log, 'MOCK_BRANCH_LOG': install_d_branch, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        p = run_cli(['install', '--email', 'ops@example.com'], env_d)
        t.ok('cli-install-version', p.returncode == 0 and pathlib.Path(install_d_branch).read_text().strip() == '3.1.4', 'install default pins stable release ref')
        for args in (['install', '--email', 'ops@example.com', '--version'], ['install', '--email', 'ops@example.com', '--branch'], ['install', '--email', 'ops@example.com', '--version', '../evil']):
            home = pathlib.Path(td) / ('install-invalid-' + str(abs(hash(tuple(args))))); home.mkdir()
            p = run_cli(args, {'HOME': str(home), 'PATH': str(fakebin), 'MOCK_INSTALL_LOG': td + '/invalid-install.args', 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')})
            t.ok('cli-install-version-errors', p.returncode == 2, 'install invalid version/branch args ' + ' '.join(args))
        p = run_cli(['install', '--version', '3.1.4', '--branch', 'master'], {'HOME': td + '/install-conflict-ref', 'PATH': str(fakebin)})
        t.ok('cli-install-version-errors', p.returncode == 2 and 'mutually exclusive' in p.stderr, 'install rejects version + branch conflict')
        p = run_cli(['install', '--cron', '--no-cron'], {'HOME': td + '/install-conflict-cron', 'PATH': str(fakebin)})
        t.ok('cli-install-errors', p.returncode == 2 and 'mutually exclusive' in p.stderr, 'install rejects cron + no-cron conflict')

        # wget fallback when curl is absent.
        wgetbin = pathlib.Path(td) / 'wgetbin'; wgetbin.mkdir()
        fakewget = wgetbin / 'wget'; fakewget.write_text('#!/bin/sh\ncat "{}"\n'.format(installer_body)); os.chmod(str(fakewget),0o755)
        for name, target in [('python3', shutil.which('python3')), ('bash', shutil.which('bash')), ('sh', shutil.which('sh')), ('cat', shutil.which('cat')), ('mkdir', shutil.which('mkdir')), ('chmod', shutil.which('chmod')), ('dirname', shutil.which('dirname')), ('cp', shutil.which('cp')), ('sed', shutil.which('sed')), ('mv', shutil.which('mv'))]: os.symlink(target, str(wgetbin / name))
        wget_home=pathlib.Path(td)/'wget-home'; wget_home.mkdir(); wget_log=td+'/wget-install.args'
        p=run_cli(['install','--email','a@example.com,b@example.com'],{'HOME':str(wget_home),'PATH':str(wgetbin),'MOCK_INSTALL_LOG':wget_log,'MOCK_INSTALL_SOURCE':MOCK,'MOCK_INSTALL_DNSAPI':str(ROOT / 'tests' / 'dnsapi')})
        t.ok('cli-install',p.returncode==0 and argvlog(wget_log)==['email=a@example.com,b@example.com','--no-cron'],'wget fallback + comma-separated email')

        nodl=pathlib.Path(td)/'no-downloader'; nodl.mkdir()
        for name, target in [('python3',shutil.which('python3')),('bash',shutil.which('bash')),('sh',shutil.which('sh')),('dirname',shutil.which('dirname')), ('cp', shutil.which('cp')), ('sed', shutil.which('sed')), ('mv', shutil.which('mv'))]: os.symlink(target,str(nodl/name))
        p=run_cli(['install','--email','ops@example.com'],{'HOME':td+'/no-downloader-home','PATH':str(nodl)})
        t.ok('cli-install-errors',p.returncode==2 and 'requires curl or wget' in p.stderr,'no curl/wget rejected')

        emptybin=pathlib.Path(td)/'empty-installer-bin'; emptybin.mkdir()
        (emptybin/'curl').write_text('#!/bin/sh\necho "exit 0"\n'); os.chmod(str(emptybin/'curl'),0o755)
        for name, target in [('python3',shutil.which('python3')),('bash',shutil.which('bash')),('sh',shutil.which('sh')),('dirname',shutil.which('dirname')), ('cp', shutil.which('cp')), ('sed', shutil.which('sed')), ('mv', shutil.which('mv'))]: os.symlink(target,str(emptybin/name))
        p=run_cli(['install','--email','ops@example.com'],{'HOME':td+'/empty-installer-home','PATH':str(emptybin)})
        t.ok('cli-install-errors',p.returncode==2 and 'installer returned success but acme.sh was not found' in p.stderr,'installer success without installed acme.sh rejected')

        failbin = pathlib.Path(td) / 'failbin'
        failbin.mkdir()
        failcurl = failbin / 'curl'
        failcurl.write_text('#!/bin/sh\nexit 7\n')
        os.chmod(str(failcurl), 0o755)
        for name, target in [('python3', shutil.which('python3')), ('bash', shutil.which('bash')), ('sh', shutil.which('sh')), ('cat', shutil.which('cat')), ('mkdir', shutil.which('mkdir')), ('chmod', shutil.which('chmod')), ('dirname', shutil.which('dirname')), ('cp', shutil.which('cp')), ('sed', shutil.which('sed')), ('mv', shutil.which('mv'))]:
            os.symlink(target, str(failbin / name))
        p = run_cli(['install', '--email', 'ops@example.com'], {'HOME': td + '/install-download-fail', 'PATH': str(failbin)})
        t.ok('cli-install-errors', p.returncode == 7 and 'download failed' in p.stderr, 'installer download rc propagated')

        scriptfailbin = pathlib.Path(td) / 'scriptfailbin'
        scriptfailbin.mkdir()
        scriptcurl = scriptfailbin / 'curl'
        scriptcurl.write_text("#!/bin/sh\nprintf '%s\\n' '#!/bin/sh' 'exit 12'\n")
        os.chmod(str(scriptcurl), 0o755)
        for name, target in [('python3', shutil.which('python3')), ('bash', shutil.which('bash')), ('sh', shutil.which('sh')), ('cat', shutil.which('cat')), ('mkdir', shutil.which('mkdir')), ('chmod', shutil.which('chmod')), ('dirname', shutil.which('dirname')), ('cp', shutil.which('cp')), ('sed', shutil.which('sed')), ('mv', shutil.which('mv'))]:
            os.symlink(target, str(scriptfailbin / name))
        p = run_cli(['install', '--email', 'ops@example.com'], {'HOME': td + '/install-script-fail', 'PATH': str(scriptfailbin)})
        t.ok('cli-install-errors', p.returncode == 12 and 'installer failed' in p.stderr, 'installer script rc propagated')

        # ----- CLI issue: defaults, all managed options/aliases/layouts/extras/errors -----
        clear(log)
        p = run_cli(['*.a.test *.b.test'], env)
        a = argvlog(log)
        prefix = ['--issue', '--server', 'letsencrypt', '--keylength', 'ec-256', '--dns', 'dns_namesilo', '--dnssleep', '120']
        t.ok('cli-issue', p.returncode == 0 and a[:9] == prefix, 'shorthand built-in defaults')
        d = pathlib.Path(out) / 'a.test'
        t.ok('cli-issue', (d / 'key.pem').exists() and (d / 'fullchain.pem').exists() and (d / 'domains.txt').exists(), 'minimal default files + manifest')
        t.ok('cli-issue', not (d / 'cert.pem').exists() and not (d / 'ca.pem').exists(), 'minimal default omits cert/ca')
        t.ok('cli-issue', (d / 'domains.txt').read_text().splitlines() == ['*.a.test', '*.b.test'], 'domains manifest exact SAN input')

        clear(log)
        p = run_cli(['issue', '*.explicit.test'], env)
        t.ok('cli-issue', p.returncode == 0 and argvlog(log)[:2] == ['--issue', '--server'], 'explicit issue command')

        canonical = ['issue', '--server', 'letsencrypt_test', '--dns', 'dns_cf', '--dnssleep', '7', '--keylength', '4096',
                     '--output-root', out, '--cert-name', 'custom', '--output-layout', 'nginx', '--reloadcmd', 'echo ok', '*.c.test']
        clear(log)
        p = run_cli(canonical, env)
        a = argvlog(log)
        t.ok('cli-issue', p.returncode == 0 and a[2:9] == ['letsencrypt_test', '--keylength', '4096', '--dns', 'dns_cf', '--dnssleep', '7'], 'canonical managed fields')
        t.ok('cli-issue', '--reloadcmd' in a and 'echo ok' in a and '--key-file' in a and any(x.endswith('/custom/privkey.pem') for x in a), 'nginx + reload mapping')

        aliases = [
            (['-server', 'letsencrypt_test', '*.alias.test'], 'server'),
            (['-dns', 'dns_cf', '*.alias.test'], 'dns'),
            (['-sleep', '9', '*.alias.test'], 'sleep'),
            (['-dnssleep', '10', '*.alias.test'], 'dnssleep'),
            (['-keylength', '2048', '*.alias.test'], 'keylength'),
            (['-k', '3072', '*.alias.test'], 'k'),
            (['-out', out, '*.alias.test'], 'out'),
            (['-name', 'aliasname', '*.alias.test'], 'name'),
            (['-format', 'minimal', '*.alias.test'], 'format'),
            (['-reload', 'true', '*.alias.test'], 'reload'),
        ]
        for args, label in aliases:
            p = run_cli(args, env)
            t.ok('cli-aliases', p.returncode == 0, label)

        layouts = {
            'full': (['cert.pem', 'key.pem', 'ca.pem', 'fullchain.pem', 'domains.txt'], []),
            'minimal': (['key.pem', 'fullchain.pem', 'domains.txt'], ['cert.pem', 'ca.pem']),
            'nginx': (['privkey.pem', 'fullchain.pem', 'domains.txt'], ['cert.pem', 'key.pem', 'ca.pem']),
            'none': ([], []),
        }
        for layout, (present, absent) in layouts.items():
            root = pathlib.Path(td) / ('layout-' + layout)
            e = dict(env)
            e['ACME_OUTPUT_ROOT'] = str(root)
            e['MOCK_LOG'] = td + '/layout-' + layout + '.argv'
            p = run_cli(['-format', layout, '*.{}.test'.format(layout)], e)
            t.ok('cli-layouts', p.returncode == 0, layout + ' rc')
            aa = argvlog(e['MOCK_LOG'])
            if layout == 'none':
                t.ok('cli-layouts', all(x not in aa for x in ['--cert-file', '--key-file', '--ca-file', '--fullchain-file']), 'none has no external paths')
            else:
                od = root / '{}.test'.format(layout)
                t.ok('cli-layouts', all((od / name).exists() for name in present), layout + ' expected files')
                t.ok('cli-layouts', all(not (od / name).exists() for name in absent), layout + ' omitted files')

        clear(log)
        p = run_cli(['*.raw.test', '11', '--', '--force', '--debug', '2'], env)
        t.ok('cli-extra', p.returncode == 0 and argvlog(log)[-3:] == ['--force', '--debug', '2'], 'raw extra after --')
        clear(log)
        p = run_cli(['issue', '--advanced', '*.adv.test'], env, 'done\n')
        t.ok('cli-extra', p.returncode == 0 and '-d' in argvlog(log), '--advanced non-TTY editor done')
        clear(log)
        # Parser branch: -- appears before domain, so spec remains absent and guided input supplies it.
        p = run_cli(['issue', '--', '--force'], env, '*.guidedpipe.test\n\n\n\n\n\nminimal\n\n\n\nn\n')
        t.ok('cli-extra', p.returncode == 0 and '--force' in argvlog(log) and '*.guidedpipe.test' in argvlog(log), '-- before domain enters guided non-TTY path')

        bad_cases = [
            (['--server'], 'missing option value'),
            (['--bogus', '*.x.test'], 'unknown wrapper option'),
            (['*.x.test', 'bad'], 'invalid delay'),
            (['-keylength', '1337', '*.x.test'], 'invalid keylength'),
            (['-format', 'wat', '*.x.test'], 'invalid layout'),
            (['-name', '../x', '*.x.test'], 'invalid cert name'),
            (['*.x.test', '120', 'extra'], 'too many args'),
            (['*.x.test', '120', '--', '--server', 'evil'], 'managed extra rejected'),
            (['*.x.test', '120', '--', '--certpath', '/tmp/x'], 'managed alias extra rejected'),
            (['*.x.test', '120', '--', '--password', 'secret'], 'secret extra rejected'),
            (['*.x.test', '120', '--', '--eab-hmac-key=secret'], 'secret equals extra rejected'),
            (['--server', '', '*.x.test'], 'empty server'),
            (['--dns', '', '*.x.test'], 'empty dns'),
            (['-out', '', '*.x.test'], 'empty output root'),
            (['-name', '.', '*.x.test'], 'dot cert name'),
            (['-name', '..', '*.x.test'], 'dotdot cert name'),
            (['-name', 'bad/name', '*.x.test'], 'slash cert name'),
            (['-format', 'none', '-name', '../ignored', '*.x.test'], 'cert name still validated even with none'),
            (['-bad'], 'single unknown option'),
        ]
        for args, label in bad_cases:
            p = run_cli(args, env)
            t.ok('cli-errors', p.returncode == 2, label)

        clear(log)
        p = run_cli(['*.fail.test', '120', '--', '--fail'], env)
        t.ok('cli-runtime', p.returncode == 17, 'upstream issue rc propagated')
        notdir = pathlib.Path(td) / 'notdir'
        notdir.write_text('x')
        p = run_cli(['-out', str(notdir), '*.ndir.test'], env)
        t.ok('cli-runtime', p.returncode == 2 and 'cannot create output directory' in p.stderr, 'output root file rejected')
        missing = run_cli(['*.x.test'], dict(env, ACME_SH_BIN=td + '/missing-acme'))
        t.ok('cli-runtime', missing.returncode == 2 and 'ACME_SH_BIN is not executable' in missing.stderr, 'invalid ACME_SH_BIN rejected')

        # ----- Persistent wrapper defaults + config/status credentials -----
        clear(wrapper)
        e_cfg = dict(env, ACME_ACCOUNT_CONF=account, ACME_WRAPPER_CONFIG=wrapper)
        p = run_cli(['config', 'defaults'], e_cfg, 'letsencrypt_test\ndns_cf\n17\n2048\n{}\nnginx\n'.format(td + '/configured'))
        t.ok('cli-config-defaults', p.returncode == 0 and pathlib.Path(wrapper).exists(), 'explicit config defaults')
        t.ok('cli-config-defaults', (os.stat(wrapper).st_mode & 0o777) == 0o600, 'wrapper config mode 600')
        p = run_cli(['defaults'], e_cfg)
        t.ok('cli-config-defaults', all(x in p.stdout for x in ['server=letsencrypt_test', 'dns=dns_cf', 'dnssleep=17', 'keylength=2048', 'output_layout=nginx']), 'persisted defaults visible')
        clear(log)
        p = run_cli(['*.configured.test'], e_cfg)
        a = argvlog(log)
        t.ok('cli-config-defaults', p.returncode == 0 and a[2:9] == ['letsencrypt_test', '--keylength', '2048', '--dns', 'dns_cf', '--dnssleep', '17'], 'persisted defaults applied to issue')
        override = dict(e_cfg, ACME_DEFAULT_SERVER='letsencrypt', ACME_DEFAULT_DNS='dns_namesilo', ACME_DEFAULT_DELAY='8',
                        ACME_DEFAULT_KEY_LENGTH='ec-384', ACME_OUTPUT_ROOT=td + '/env-out', ACME_OUTPUT_LAYOUT='minimal')
        p = run_cli(['defaults'], override)
        t.ok('cli-config-defaults', all(x in p.stdout for x in ['server=letsencrypt', 'dns=dns_namesilo', 'dnssleep=8', 'keylength=ec-384', 'output_layout=minimal']), 'environment overrides persisted defaults')

        # config without target defaults to wrapper defaults; invalid target retries.
        wrapper2 = td + '/wrapper2.ini'
        e = dict(e_cfg, ACME_WRAPPER_CONFIG=wrapper2)
        p = run_cli(['config'], e, 'bad\ndefaults\n\n\n\n\n{}\nminimal\n'.format(td + '/cfg2'))
        t.ok('cli-config-defaults', p.returncode == 0 and pathlib.Path(wrapper2).exists() and 'enter defaults' in p.stderr, 'config target invalid -> retry -> defaults')

        clear(account)
        p = run_cli(['status'], e_cfg)
        t.ok('cli-config-creds', p.returncode == 0 and 'configured_provider_list=empty' in p.stdout and 'dns_provider_total=7' in p.stdout, 'status no credentials')
        p = run_cli(['config', 'dns_namesilo'], e_cfg, 'NSKEY\n')
        t.ok('cli-config-creds', p.returncode == 0, 'NameSilo config')
        p = run_cli(['config', 'dns_cf'], e_cfg, '2\nCFTOKEN\nCFACCOUNT\n\n')
        t.ok('cli-config-creds', p.returncode == 0, 'Cloudflare config')
        p = run_cli(['config', 'dns_gd'], e_cfg, 'GDKEY\nGDSECRET\n')
        t.ok('cli-config-creds', p.returncode == 0, 'GoDaddy config')
        p = run_cli(['status'], e_cfg)
        t.ok('cli-config-creds', p.returncode == 0 and all(x in p.stdout for x in ['dns_namesilo=configured', 'dns_cf=configured', 'dns_gd=configured']) and 'GDSECRET' not in p.stdout + p.stderr, 'status all configured/no secret')

        # wrapper config error branches.
        real = pathlib.Path(td) / 'real-wrapper.ini'
        real.write_text('[defaults]\nserver = keep\n')
        os.chmod(str(real), 0o600)
        link = pathlib.Path(td) / 'link-wrapper.ini'
        os.symlink(str(real), str(link))
        p = run_cli(['config', 'defaults'], dict(e_cfg, ACME_WRAPPER_CONFIG=str(link)), '\n\n\n\n{}\nminimal\n'.format(td + '/x'))
        t.ok('cli-config-errors', p.returncode == 2 and 'refusing symlinked wrapper config' in p.stderr and 'keep' in real.read_text(), 'wrapper config symlink refused')
        malformed_cfg = pathlib.Path(td) / 'bad-wrapper.ini'
        malformed_cfg.write_text('[defaults\nserver = x\n')
        p = run_cli(['defaults'], dict(e_cfg, ACME_WRAPPER_CONFIG=str(malformed_cfg)))
        t.ok('cli-config-errors', p.returncode == 2 and 'cannot read wrapper config' in p.stderr, 'malformed wrapper config rejected')

        # ----- Dynamic provider public branches -----
        p = run_cli(['providers'], env)
        t.ok('cli-providers', p.returncode == 0 and all(x in p.stdout for x in ['dns_namesilo', 'dns_cf', 'dns_gd', 'dns_raw', 'dns_runtime', 'dns_alt', 'dns_legacy']), 'providers lists every installed fixture driver')
        p = run_cli(['providers', 'cloud'], env)
        t.ok('cli-providers', p.returncode == 0 and 'dns_cf' in p.stdout and 'dns_gd' not in p.stdout, 'providers query filter')
        p = run_cli(['providers', 'does-not-exist'], env)
        t.ok('cli-providers', p.returncode == 2 and 'no DNS providers matched' in p.stderr, 'providers no-match explicit failure')
        p = run_cli(['providers', 'a', 'b'], env)
        t.ok('cli-providers', p.returncode == 2 and 'at most one' in p.stderr, 'providers rejects extra query')
        p = run_cli(['status', '--all'], e_cfg)
        t.ok('cli-provider-status', p.returncode == 0 and 'dns_provider_total=7' in p.stdout and 'dns_runtime=runtime-only' in p.stdout and 'dns_legacy=manual-schema' in p.stdout, 'status --all covers runtime/manual schemas')
        p = run_cli(['status', 'cloud'], e_cfg)
        t.ok('cli-provider-status', p.returncode == 0 and 'dns_cf=' in p.stdout and 'dns_gd=' not in p.stdout, 'status provider query')
        p = run_cli(['config', 'dns_raw'], e_cfg, 'RAW-TOKEN\n')
        t.ok('cli-provider-config', p.returncode == 0 and 'RAW_TOKEN=' in pathlib.Path(account).read_text(), 'raw persistence provider config')
        before_runtime = pathlib.Path(account).read_text()
        p = run_cli(['config', 'dns_runtime'], e_cfg)
        t.ok('cli-provider-config', p.returncode == 0 and pathlib.Path(account).read_text() == before_runtime and 'runtime-only' in p.stderr, 'runtime-only provider is explained and not persisted')
        p = run_cli(['config', 'dns_legacy'], e_cfg)
        t.ok('cli-provider-config', p.returncode == 0 and 'structured Options metadata' in p.stderr, 'legacy provider manual-schema fallback')
        p = run_cli(['config', 'dns_alt'], e_cfg, '2\nALT-USER\nALT-PASS\n')
        t.ok('cli-provider-config', p.returncode == 0 and 'SAVED_ALT_USER=' in pathlib.Path(account).read_text() and 'SAVED_ALT_PASS=' in pathlib.Path(account).read_text(), 'generic OptionsAlt credential group')

        # ----- CLI cron + managed certificate/SAN UX -----
        p = run_cli(['cron', 'status'], cron_env)
        t.ok('cli-cron', p.returncode == 0 and 'cron=disabled' in p.stdout, 'cron default/status off')
        p = run_cli(['cron', 'on'], cron_env)
        t.ok('cli-cron', p.returncode == 0 and cron_state.read_text().strip() == 'enabled', 'cron on delegates upstream')
        p = run_cli(['cron', 'status'], cron_env)
        t.ok('cli-cron', p.returncode == 0 and 'cron=enabled' in p.stdout and 'entry=' in p.stdout, 'cron status detects entry')
        clear(log); p = run_cli(['cron', 'run'], cron_env)
        t.ok('cli-cron', p.returncode == 0 and argvlog(log) == ['--cron'], 'cron run delegates upstream')
        p = run_cli(['cron', 'off'], cron_env)
        t.ok('cli-cron', p.returncode == 0 and cron_state.read_text().strip() == 'disabled', 'cron off delegates upstream')
        p = run_cli(['cron', 'bogus'], cron_env)
        t.ok('cli-cron-errors', p.returncode == 2 and 'status, on, off or run' in p.stderr, 'cron invalid action rejected')

        p = run_cli(['certs', 'list'], env)
        t.ok('cli-certs', p.returncode == 0 and '*.aa.test, *.bb.test, *.cc.test' in p.stdout and 'dns_namesilo' in p.stdout and 'example.test, www.example.test' in p.stdout and 'dns_cf' in p.stdout, 'list shows all SANs and saved provider')
        p = run_cli(['certs', 'read', '*.bb.test'], env)
        t.ok('cli-certs', p.returncode == 0 and 'Main domain: *.aa.test' in p.stdout and 'DNS provider(s): dns_namesilo' in p.stdout and 'Fullchain output: /etc/ssl/acme/aa/fullchain.pem' in p.stdout, 'read SAN selector')
        clear(log); p = run_cli(['certs', 'update', '*.aa.test'], env)
        t.ok('cli-certs', p.returncode == 0 and argvlog(log) == ['--renew', '-d', '*.aa.test', '--ecc'], 'update uses saved config')
        clear(log); p = run_cli(['certs', 'renew', '*.aa.test', '--force'], env)
        t.ok('cli-certs', p.returncode == 0 and argvlog(log) == ['--renew', '-d', '*.aa.test', '--ecc', '--force'], 'forced update explicit')
        p = run_cli(['certs', 'delete', 'example.test'], env)
        t.ok('cli-certs-errors', p.returncode == 2 and 'requires --yes' in p.stderr, 'non-interactive delete needs --yes')
        clear(log); p = run_cli(['certs', 'delete', 'example.test', '--yes'], env)
        t.ok('cli-certs', p.returncode == 0 and argvlog(log) == ['--remove', '-d', 'example.test'], 'delete delegates remove')
        p = run_cli(['certs', 'read'], env)
        t.ok('cli-certs-errors', p.returncode == 2 and 'requires DOMAIN or list index' in p.stderr, 'noninteractive selector required')
        p = run_cli(['certs', 'read', '*.aa.test', '--force'], env)
        t.ok('cli-certs-errors', p.returncode == 2 and '--force is only valid' in p.stderr, 'force scope validated')

        # ----- v1.7 full acme.sh friendly surface -----
        issue_modes = [
            (['issue', '--validation', 'webroot', '--webroot', '/srv/www', 'mode.test'], ['--webroot', '/srv/www']),
            (['issue', '--standalone', 'mode.test'], ['--standalone']),
            (['issue', '--alpn', 'mode.test'], ['--alpn']),
            (['issue', '--stateless', 'mode.test'], ['--stateless']),
            (['issue', '--apache', 'mode.test'], ['--apache']),
            (['issue', '--nginx', '--nginx-config', '/etc/nginx/nginx.conf', 'mode.test'], ['--nginx', '/etc/nginx/nginx.conf']),
            (['issue', '--manual-dns', 'mode.test'], ['--dns', '--yes-I-know-dns-manual-mode-enough-go-ahead-please']),
            (['issue', '--dns-persist', 'mode.test'], ['--dns-persist']),
        ]
        for args, expected in issue_modes:
            clear(log); p = run_cli(args, env); a = argvlog(log)
            t.ok('cli-issue-modes', p.returncode == 0 and all(x in a for x in expected), '{} delegates upstream validation'.format(args[1]))

        clear(log); p = run_cli(['certs', 'renew-all', '--force'], env)
        t.ok('cli-certs-lifecycle', p.returncode == 0 and argvlog(log) == ['--renew-all', '--force'], 'renew-all delegates upstream')
        install_root = td + '/cert-install'
        clear(log); p = run_cli(['certs', 'install', '*.aa.test', '--layout', 'minimal', '--output-root', install_root], env)
        t.ok('cli-certs-lifecycle', p.returncode == 0 and argvlog(log)[:4] == ['--install-cert', '-d', '*.aa.test', '--ecc'] and pathlib.Path(install_root, 'aa.test', 'domains.txt').exists(), 'install-cert lifecycle + SAN manifest')
        clear(log); p = run_cli(['certs', 'deploy', '*.aa.test', '--hook', 'testdeploy', '--yes'], env)
        t.ok('cli-certs-lifecycle', p.returncode == 0 and argvlog(log) == ['--deploy', '-d', '*.aa.test', '--deploy-hook', 'testdeploy', '--ecc'], 'certificate deploy hook')
        clear(log); p = run_cli(['certs', 'revoke', '*.aa.test', '--reason', '1', '--yes'], env)
        t.ok('cli-certs-lifecycle', p.returncode == 0 and argvlog(log) == ['--revoke', '-d', '*.aa.test', '--ecc', '--revoke-reason', '1'], 'revoke with reason')
        clear(log); p = run_cli(['certs', 'deactivate-auth', '*.aa.test', '--yes'], env)
        t.ok('cli-certs-lifecycle', p.returncode == 0 and argvlog(log) == ['--deactivate', '-d', '*.aa.test', '--ecc'], 'deactivate authorization')
        p = run_cli(['certs', 'revoke', '*.aa.test'], env)
        t.ok('cli-certs-lifecycle-errors', p.returncode == 2 and 'requires --yes' in p.stderr, 'revoke noninteractive confirmation enforced')

        for kind, expected in [('dns','dns_namesilo'), ('deploy','testdeploy'), ('notify','testnotify')]:
            p = run_cli(['hooks', kind], env)
            t.ok('cli-hooks', p.returncode == 0 and expected in p.stdout, '{} hooks dynamically listed'.format(kind))
        clear(log); p = run_cli(['deploy', '*.aa.test', '--hook', 'testdeploy', '--yes'], env)
        t.ok('cli-deploy', p.returncode == 0 and '--deploy-hook' in argvlog(log) and 'testdeploy' in argvlog(log), 'top-level deploy friendly route')
        p = run_cli(['deploy', '*.aa.test', '--hook', 'missing', '--yes'], env)
        t.ok('cli-deploy-errors', p.returncode == 2 and 'hook not found' in p.stderr, 'unknown deploy hook rejected')

        p = run_cli(['notify', 'hooks'], env)
        t.ok('cli-notify', p.returncode == 0 and 'testnotify' in p.stdout, 'notify hooks route')
        clear(log); p = run_cli(['notify', 'set', '--hook', 'testnotify', '--level', '2', '--mode', '0', '--source', 'helper'], env)
        t.ok('cli-notify', p.returncode == 0 and argvlog(log) == ['--set-notify', '--notify-hook', 'testnotify', '--notify-level', '2', '--notify-mode', '0', '--notify-source', 'helper'] and 'test notification' in p.stderr, 'notify set delegates and warns about live test')
        p = run_cli(['notify', 'set', '--level', '9'], env)
        t.ok('cli-notify-errors', p.returncode == 2, 'invalid notify level rejected')

        p = run_cli(['account', 'status'], env)
        t.ok('cli-account', p.returncode == 0 and 'account_conf=' in p.stdout, 'account status')
        clear(log); p = run_cli(['account', 'register', '--server', 'letsencrypt', '--email', 'ops@example.com'], env)
        t.ok('cli-account', p.returncode == 0 and argvlog(log) == ['--register-account', '--server', 'letsencrypt', '--email', 'ops@example.com'], 'account register')
        clear(log); p = run_cli(['account', 'update', '--server', 'letsencrypt', '--email', 'next@example.com'], env)
        t.ok('cli-account', p.returncode == 0 and argvlog(log) == ['--update-account', '--server', 'letsencrypt', '--email', 'next@example.com'], 'account update')
        clear(log); p = run_cli(['account', 'key', '--server', 'letsencrypt', '--accountkeylength', 'ec-384'], env)
        t.ok('cli-account', p.returncode == 0 and argvlog(log) == ['--update-account-key', '--server', 'letsencrypt', '--accountkeylength', 'ec-384'], 'account key rotation')
        clear(log); p = run_cli(['account', 'deactivate', '--server', 'letsencrypt', '--yes'], env)
        t.ok('cli-account', p.returncode == 0 and argvlog(log) == ['--deactivate-account', '--server', 'letsencrypt'], 'account deactivate')

        clear(log); p = run_cli(['csr', 'show', '/tmp/test.csr'], env)
        t.ok('cli-csr', p.returncode == 0 and argvlog(log) == ['--show-csr', '--csr', '/tmp/test.csr'], 'CSR show')
        clear(log); p = run_cli(['csr', 'sign', '/tmp/test.csr', '--dns', 'dns_namesilo'], env)
        t.ok('cli-csr', p.returncode == 0 and argvlog(log) == ['--sign-csr', '--csr', '/tmp/test.csr', '--server', 'letsencrypt_test', '--dns', 'dns_namesilo'], 'CSR sign DNS')
        clear(log); p = run_cli(['csr', 'create', 'a.test b.test', '--keylength', 'ec-256'], env)
        t.ok('cli-csr', p.returncode == 0 and argvlog(log) == ['--create-csr', '--keylength', 'ec-256', '-d', 'a.test', '-d', 'b.test'], 'CSR create')
        clear(log); p = run_cli(['csr', 'domain-key', 'a.test', '--keylength', '2048'], env)
        t.ok('cli-csr', p.returncode == 0 and '--create-domain-key' in argvlog(log), 'domain key create')
        clear(log); p = run_cli(['csr', 'account-key', 'ec-384'], env)
        t.ok('cli-csr', p.returncode == 0 and argvlog(log) == ['--create-account-key', '--accountkeylength', 'ec-384'], 'account key create')

        clear(log); secret = 'PFX-FLOW-SECRET'; p = run_cli(['export', 'pkcs12', '*.aa.test', '--password-stdin'], env, secret + '\n')
        t.ok('cli-export', p.returncode == 0 and '--to-pkcs12' in argvlog(log) and secret in argvlog(log) and secret not in p.stdout + p.stderr, 'PKCS12 hidden stdin password')
        clear(log); p = run_cli(['export', 'pkcs8', '*.aa.test'], env)
        t.ok('cli-export', p.returncode == 0 and argvlog(log) == ['--to-pkcs8', '-d', '*.aa.test', '--ecc'], 'PKCS8 export')

        clear(log); p = run_cli(['ca', 'default', 'letsencrypt'], env)
        t.ok('cli-ca', p.returncode == 0 and argvlog(log) == ['--set-default-ca', '--server', 'letsencrypt'], 'set default CA')
        clear(log); p = run_cli(['ca', 'chain', 'letsencrypt', 'ISRGRootX1'], env)
        t.ok('cli-ca', p.returncode == 0 and '--preferred-chain' in argvlog(log), 'set preferred chain')
        clear(log); p = run_cli(['ca', 'profiles', 'letsencrypt'], env)
        t.ok('cli-ca', p.returncode == 0 and argvlog(log) == ['--list-profiles', '--server', 'letsencrypt'], 'list profiles completion-visible route')
        clear(log); p = run_cli(['ca', 'dns-persist', 'a.test *.a.test', '--wildcard', '--ca-name', 'ca.test', '--days', '30'], env)
        a = argvlog(log)
        t.ok('cli-ca', p.returncode == 0 and '--dns-persist-wildcard' in a and '--dns-persist-ca-name' in a and '--dns-persist-days' in a, 'dns-persist full options')

        p = run_cli(['uninstall'], env)
        t.ok('cli-uninstall-errors', p.returncode == 2 and 'requires --yes' in p.stderr, 'uninstall noninteractive confirmation enforced')
        clear(log); p = run_cli(['uninstall', '--yes'], env)
        t.ok('cli-uninstall', p.returncode == 0 and argvlog(log) == ['--uninstall'] and 'Helper will not additionally remove' in p.stderr, 'uninstall delegates upstream without purge')

        # ----- Version-management public branches -----
        vh = pathlib.Path(td) / 'version-flow-home'; vh.mkdir()
        v_acme = vh / 'acme.sh'; shutil.copy2(MOCK, str(v_acme)); os.chmod(str(v_acme), 0o755)
        shutil.copytree(str(ROOT / 'tests' / 'dnsapi'), str(vh / 'dnsapi'))
        venv = dict(env, ACME_SH_BIN=str(v_acme), ACME_VERSION_BACKUP_DIR=td + '/version-flow-backups', MOCK_HISTORY=td + '/version-flow-history', MOCK_LOG=td + '/version-flow-argv')
        p = run_cli(['versions'], venv)
        t.ok('cli-version-manager', p.returncode == 0 and 'current=3.1.5' in p.stdout and 'stable_target=3.1.4' in p.stdout and 'interface_reference=3.1.5' in p.stdout and 'backups=0' in p.stdout, 'versions inventory before switch')
        p = run_cli(['versions', 'x'], venv)
        t.ok('cli-version-manager-errors', p.returncode == 2, 'versions rejects extra')
        for args in (['switch'], ['switch', 'a', 'b'], ['switch', '../evil'], ['rollback', 'a', 'b']):
            p = run_cli(args, venv, '' if args == ['switch'] else None)
            t.ok('cli-version-manager-errors', p.returncode in (1, 2), 'invalid version-manager invocation ' + ' '.join(args))
        p = run_cli(['rollback'], venv)
        t.ok('cli-version-manager-errors', p.returncode == 2 and 'no version backups available' in p.stderr, 'rollback without backup fails explicitly')
        p = run_cli(['switch', '3.1.4'], venv)
        t.ok('cli-version-manager', p.returncode == 0 and 'acme_sh_version=3.1.4' in run_cli(['version'], venv).stdout, 'switch explicit release downgrade')
        p = run_cli(['versions'], venv)
        t.ok('cli-version-manager', p.returncode == 0 and 'backups=1' in p.stdout and 'backup=' in p.stdout, 'switch creates visible backup')
        p = run_cli(['rollback', 'not-a-backup'], venv)
        t.ok('cli-version-manager-errors', p.returncode == 2 and 'backup not found' in p.stderr, 'rollback rejects unknown id')
        p = run_cli(['update', '--version', '3.1.4'], venv)
        t.ok('cli-version-manager', p.returncode == 0 and 'acme_sh_version=3.1.4' in run_cli(['version'], venv).stdout, 'update --version explicit stable release')
        t.ok('cli-version-manager', 'already on v3.1.4' in (p.stdout + p.stderr), 'same-version update is a no-op')
        p = run_cli(['update', '--help'], venv)
        t.ok('cli-version-manager', p.returncode == 0 and 'Usage: acme update' in p.stderr, 'update help')
        for args in (['update', '--version'], ['update', '--branch'], ['update', '--bogus', 'x']):
            p = run_cli(args, venv)
            t.ok('cli-version-manager-errors', p.returncode == 2, 'update invalid args ' + ' '.join(args))
        e_master = dict(venv, MOCK_UPGRADE_VERSION='3.1.6')
        p = run_cli(['update', '--branch', 'master'], e_master)
        t.ok('cli-version-manager', p.returncode == 0 and 'acme_sh_version=3.1.6' in run_cli(['version'], venv).stdout, 'update --branch master accepts probed-compatible version')
        p = run_cli(['update'], venv)
        t.ok('cli-version-manager', p.returncode == 0 and 'acme_sh_version=3.1.4' in run_cli(['version'], venv).stdout, 'default update returns to pinned stable ref')
        p = run_cli(['rollback'], venv)
        t.ok('cli-version-manager', p.returncode in (0, 3) and 'rollback restored' in p.stderr, 'rollback latest backup public path')

        # ----- update/native CLI branches -----
        clear(log)
        p = run_cli(['update'], env)
        t.ok('cli-native', p.returncode == 0 and any(line == 'CALL\t--upgrade\t--branch\t3.1.4' for line in pathlib.Path(env['MOCK_HISTORY']).read_text().splitlines()), 'update -> pinned stable ref without forced redownload')
        p = run_cli(['update', '--branch', 'master'], dict(env, MOCK_UPGRADE_FAIL='1'))
        t.ok('cli-native', p.returncode == 23 and 'rollback restored' in p.stderr, 'update upstream rc propagated + rollback')
        clear(log)
        p = run_cli(['native', '--info', '--debug', '2'], env)
        t.ok('cli-native', p.returncode == 0 and argvlog(log) == ['--info', '--debug', '2'], 'native direct exact passthrough')

        badhelp = make_mock(td, 'if [[ "${1:-}" == "--help" ]]; then echo nope; exit 19; fi\nexit 0\n', 'badhelp.sh')
        p = run_cli(['native'], {'ACME_SH_BIN': badhelp}, '')
        t.ok('cli-native-errors', p.returncode == 2 and 'exit 19' in p.stderr, 'nonzero --help rejected')
        malformed_help = make_mock(td, 'if [[ "${1:-}" == "--help" ]]; then echo "Usage only"; exit 0; fi\nexit 0\n', 'malformed-help.sh')
        p = run_cli(['native'], {'ACME_SH_BIN': malformed_help}, '')
        t.ok('cli-native-errors', p.returncode == 2 and 'cannot parse' in p.stderr, 'malformed --help rejected')

        # Native interactive non-TTY: execute and cancel.
        clear(log)
        info_idx = idx(COMMANDS, '--info')
        p = run_cli(['native'], env, '{}\ndone\ny\n'.format(info_idx))
        t.ok('cli-native-interactive', p.returncode == 0 and argvlog(log) == ['--info'] and 'Purpose' in p.stderr, 'native non-TTY execute + command guidance')
        clear(log)
        p = run_cli(['native'], env, '{}\ndone\nn\n'.format(info_idx))
        t.ok('cli-native-interactive', p.returncode == 0 and not pathlib.Path(log).exists() and 'cancelled' in p.stderr, 'native non-TTY cancel')

        # Every public upstream command is selectable and receives Chinese guidance.
        for command_index, command in enumerate(COMMANDS, 1):
            clear(log)
            p = run_cli(['native'], env, '{}\ndone\nn\n'.format(command_index))
            t.ok('native-command-coverage', p.returncode == 0 and 'Purpose:' in p.stderr and 'No dedicated Helper guidance' not in p.stderr and not pathlib.Path(log).exists(), '{} guided/cancel branch'.format(command))

        # ----- PTY main menu: invalid retry + all actions -----
        def main_defaults(s):
            s.expect(MAIN_PROMPT).line('wat')
            s.expect('Invalid selection').expect(MAIN_PROMPT).line('defaults')
        pty_case(t, 'pty-main', 'invalid main action retries -> defaults', [], env, main_defaults,
                 lambda rc, text: rc == 0 and 'server=letsencrypt' in text)

        def main_status(s):
            s.expect(MAIN_PROMPT).line('status')
        pty_case(t, 'pty-main', 'main status branch', [], env, main_status,
                 lambda rc, text: rc == 0 and 'dns_provider_total=7' in text)

        def main_version(s):
            s.expect(MAIN_PROMPT).line('version')
        pty_case(t, 'pty-main', 'main version branch', [], env, main_version,
                 lambda rc, text: rc == 0 and 'wrapper_version=' + VERSION in text and 'acme_sh_compatibility=probed-compatible' in text)

        def main_providers(s):
            s.expect(MAIN_PROMPT).line('providers')
            s.expect('Search providers').line('cloud')
        pty_case(t, 'pty-main', 'main providers search branch', [], env, main_providers,
                 lambda rc, text: rc == 0 and 'dns_cf' in text and 'dns_gd' not in text)

        def main_versions(s):
            s.expect(MAIN_PROMPT).line('versions')
        pty_case(t, 'pty-main', 'main versions branch', [], env, main_versions,
                 lambda rc, text: rc == 0 and 'current=' in text and 'stable_target=3.1.4' in text and 'interface_reference=3.1.5' in text and 'backup_root=' in text)

        pty_fakebin = pathlib.Path(td) / 'pty-fakebin'
        pty_fakebin.mkdir()
        pty_installer = pathlib.Path(td) / 'pty-installer.sh'
        pty_installer.write_text(installer_body.read_text())
        pty_curl = pty_fakebin / 'curl'
        pty_curl.write_text('#!/bin/sh\ncat "{}"\n'.format(pty_installer))
        os.chmod(str(pty_curl), 0o755)
        for name, target in [('python3', shutil.which('python3')), ('bash', shutil.which('bash')), ('sh', shutil.which('sh')), ('cat', shutil.which('cat')), ('mkdir', shutil.which('mkdir')), ('chmod', shutil.which('chmod')), ('dirname', shutil.which('dirname')), ('cp', shutil.which('cp')), ('sed', shutil.which('sed')), ('mv', shutil.which('mv'))]:
            os.symlink(target, str(pty_fakebin / name))
        pty_install_home = pathlib.Path(td) / 'pty-install-home'
        pty_install_home.mkdir()
        pty_install_log = td + '/pty-install.args'
        pty_install_env = {'HOME': str(pty_install_home), 'PATH': str(pty_fakebin), 'MOCK_INSTALL_LOG': pty_install_log, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        def main_install(s):
            s.expect(MAIN_PROMPT).line('install')
            s.expect('ACME account email').line('bad*email')
            s.expect('email must be one or more').expect('ACME account email').line('pty@example.com')
            s.expect('acme.sh version/tag/branch').line('../bad')
            s.expect('invalid upstream version/branch').expect('acme.sh version/tag/branch').line('')
            s.expect('Install automatic-renewal cron').line('y')
            s.expect('Add a shell-profile alias').line('n')
            s.expect('Download and run the official installer').line('y')
        pty_case(t, 'pty-main', 'main install invalid email/ref retry then success branch', [], pty_install_env, main_install,
                 lambda rc, text: rc == 0 and (pty_install_home / '.acme.sh' / 'acme.sh').exists() and argvlog(pty_install_log) == ['email=pty@example.com', '--no-profile'])

        pty_blank_home = pathlib.Path(td) / 'pty-install-blank-email-home'; pty_blank_home.mkdir()
        pty_blank_log = td + '/pty-install-blank-email.args'
        pty_blank_env = {'HOME': str(pty_blank_home), 'PATH': str(pty_fakebin), 'MOCK_INSTALL_LOG': pty_blank_log, 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        def main_install_blank_email(s):
            s.expect(MAIN_PROMPT).line('install')
            s.expect('ACME account email').line('')
            s.expect('acme.sh version/tag/branch').line('')
            s.expect('Install automatic-renewal cron').line('')
            s.expect('Add a shell-profile alias').line('n')
            s.expect('Download and run the official installer').line('y')
        pty_case(t, 'pty-main', 'main install blank email + default cron off', [], pty_blank_env, main_install_blank_email,
                 lambda rc, text: rc == 0 and (pty_blank_home / '.acme.sh' / 'acme.sh').exists() and argvlog(pty_blank_log) == ['--no-cron', '--no-profile'])

        pty_cancel_home = pathlib.Path(td) / 'pty-install-cancel-home'
        pty_cancel_home.mkdir()
        pty_cancel_env = {'HOME': str(pty_cancel_home), 'PATH': str(pty_fakebin), 'MOCK_INSTALL_LOG': td + '/pty-install-cancel.args', 'MOCK_INSTALL_SOURCE': MOCK, 'MOCK_INSTALL_DNSAPI': str(ROOT / 'tests' / 'dnsapi')}
        def main_install_cancel(s):
            s.expect(MAIN_PROMPT).line('install')
            s.expect('ACME account email').line('pty@example.com')
            s.expect('acme.sh version/tag/branch').line('')
            s.expect('Install automatic-renewal cron').line('y')
            s.expect('Add a shell-profile alias').line('y')
            s.expect('Download and run the official installer').line('n')
        pty_case(t, 'pty-main', 'main install cancel branch', [], pty_cancel_env, main_install_cancel,
                 lambda rc, text: rc == 0 and 'cancelled' in text and not (pty_cancel_home / '.acme.sh' / 'acme.sh').exists())

        pu_home = pathlib.Path(td) / 'pty-update-home'; pu_home.mkdir()
        pu_acme = pu_home / 'acme.sh'; shutil.copy2(MOCK, str(pu_acme)); os.chmod(str(pu_acme), 0o755)
        shutil.copytree(str(ROOT / 'tests' / 'dnsapi'), str(pu_home / 'dnsapi'))
        e_update = dict(env, ACME_SH_BIN=str(pu_acme), ACME_VERSION_BACKUP_DIR=td + '/pty-update-backups', MOCK_HISTORY=td + '/pty-update-history', MOCK_LOG=td + '/pty-update.argv')
        def main_update(s):
            s.expect(MAIN_PROMPT).line('update')
            s.expect('Confirm the version switch').line('y')
        pty_case(t, 'pty-main', 'main update branch', [], e_update, main_update,
                 lambda rc, text: rc == 0 and 'reported version 3.1.4' in text)

        # Interactive switch + rollback public branches use an isolated upstream copy.
        pv_home = pathlib.Path(td) / 'pty-version-home'; pv_home.mkdir()
        pv_acme = pv_home / 'acme.sh'; shutil.copy2(MOCK, str(pv_acme)); os.chmod(str(pv_acme), 0o755)
        shutil.copytree(str(ROOT / 'tests' / 'dnsapi'), str(pv_home / 'dnsapi'))
        pv_env = dict(env, ACME_SH_BIN=str(pv_acme), ACME_VERSION_BACKUP_DIR=td + '/pty-version-backups', MOCK_HISTORY=td + '/pty-version-history', MOCK_LOG=td + '/pty-version-argv')
        def main_switch(s):
            s.expect(MAIN_PROMPT).line('switch')
            s.expect('Target version/tag/branch').line('../bad')
            s.expect('invalid upstream version/branch').expect('Target version/tag/branch').line('3.1.4')
            s.expect('Confirm the version switch').line('y')
        pty_case(t, 'pty-main-version', 'main switch invalid ref retry then confirm branch', [], pv_env, main_switch,
                 lambda rc, text: rc == 0 and 'reported version 3.1.4' in text)
        def main_switch_cancel(s):
            s.expect(MAIN_PROMPT).line('switch')
            s.expect('Target version/tag/branch').line('master')
            s.expect('Confirm the version switch').line('n')
        pty_case(t, 'pty-main-version', 'main switch interactive cancel branch', [], pv_env, main_switch_cancel,
                 lambda rc, text: rc == 0 and 'cancelled' in text)
        def main_rollback(s):
            s.expect(MAIN_PROMPT).line('rollback')
            s.expect('backup id').line('')
            s.expect('Confirm rollback').line('y')
        pty_case(t, 'pty-main-version', 'main rollback latest branch', [], pv_env, main_rollback,
                 lambda rc, text: rc in (0, 3) and 'rollback restored' in text)
        def main_rollback_cancel(s):
            s.expect(MAIN_PROMPT).line('rollback')
            s.expect('backup id').line('')
            s.expect('Confirm rollback').line('n')
        pty_case(t, 'pty-main-version', 'main rollback cancel branch', [], pv_env, main_rollback_cancel,
                 lambda rc, text: rc == 0 and 'cancelled' in text)

        # ----- PTY cert/SAN and cron branches -----
        def main_certs_read(s):
            s.expect(MAIN_PROMPT).line('certs')
            s.expect('1. *.aa.test').expect('domains: *.aa.test, *.bb.test, *.cc.test').expect('Certificate number').line('1')
            s.expect('Certificate action').line('read')
        pty_case(t, 'pty-certs', 'SAN list select + read', [], env, main_certs_read,
                 lambda rc, text: rc == 0 and 'DNS provider(s): dns_namesilo' in text and '  - *.cc.test' in text)

        clear(log)
        def main_certs_update(s):
            s.expect(MAIN_PROMPT).line('certs')
            s.expect('Certificate number').line('1').expect('Certificate action').line('update')
            s.expect('Force renewal now').line('n')
        pty_case(t, 'pty-certs', 'SAN list select + update', [], env, main_certs_update,
                 lambda rc, text: rc == 0 and argvlog(log) == ['--renew', '-d', '*.aa.test', '--ecc'])

        clear(log)
        def main_certs_delete_cancel(s):
            s.expect(MAIN_PROMPT).line('certs')
            s.expect('Certificate number').line('2').expect('Certificate action').line('delete')
            s.expect('Confirm removal of example.test').line('n')
        pty_case(t, 'pty-certs', 'SAN list delete cancel', [], env, main_certs_delete_cancel,
                 lambda rc, text: rc == 0 and 'cancelled' in text and (not argvlog(log) or argvlog(log)[0] != '--remove'))

        cron_state.write_text('disabled\n')
        def main_cron_on(s):
            s.expect(MAIN_PROMPT).line('cron')
            s.expect('Current cron: disabled').expect('Scheduling action').line('on')
        pty_case(t, 'pty-cron', 'cron switch on', [], cron_env, main_cron_on,
                 lambda rc, text: rc == 0 and cron_state.read_text().strip() == 'enabled')

        # ----- PTY v1.7 complete friendly surface -----
        clear(log)
        def drv_uninstall_cancel(s):
            s.expect('Uninstall acme.sh and its upstream cron job').line('n')
        pty_case(t, 'pty-uninstall', 'upstream uninstall cancel', ['uninstall'], env, drv_uninstall_cancel,
                 lambda rc, text: rc == 0 and 'cancelled' in text and (not argvlog(log) or argvlog(log)[0] != '--uninstall'))
        clear(log)
        def drv_uninstall_yes(s):
            s.expect('Uninstall acme.sh and its upstream cron job').line('y')
        pty_case(t, 'pty-uninstall', 'upstream uninstall confirm', ['uninstall'], env, drv_uninstall_yes,
                 lambda rc, text: rc == 0 and argvlog(log) == ['--uninstall'])

        clear(log)
        deploy_env_log = pathlib.Path(td) / 'deploy-hook-env.log'
        deploy_env = dict(env, MOCK_ENV_LOG=str(deploy_env_log))
        def drv_deploy(s):
            s.expect('Certificate number').line('1')
            s.expect('Select a deploy hook').line('1')
            s.expect('Enter or override variables for this hook invocation').line('y')
            s.expect('TESTDEPLOY_TOKEN').line('DEPLOY-PTY-SECRET')
            s.expect('TESTDEPLOY_HOST').line('deploy-host')
            s.expect('Execute this deploy hook').line('y')
        pty_case(t, 'pty-deploy', 'select cert + dynamic deploy hook + hook env wizard', ['deploy'], deploy_env, drv_deploy,
                 lambda rc, text: rc == 0 and '--deploy-hook' in argvlog(log) and 'testdeploy' in argvlog(log) and 'DEPLOY-PTY-SECRET' not in text and deploy_env_log.exists() and 'TESTDEPLOY_TOKEN=DEPLOY-PTY-SECRET' in deploy_env_log.read_text() and 'TESTDEPLOY_HOST=deploy-host' in deploy_env_log.read_text())

        def drv_notify_status(s):
            s.expect('Notification action').line('status')
        pty_case(t, 'pty-notify', 'notify status interactive', ['notify'], env, drv_notify_status,
                 lambda rc, text: rc == 0 and 'notify_hook=' in text)
        clear(log)
        notify_env_log = pathlib.Path(td) / 'notify-hook-env.log'
        notify_env = dict(env, MOCK_ENV_LOG=str(notify_env_log))
        def drv_notify_set(s):
            s.expect('Notification action').line('set')
            s.expect('Select a notification hook').line('1')
            s.expect('Notification level').line('2')
            s.expect('Notification mode').line('0')
            s.expect('Notification source name').line('helper-pty')
            s.expect('Enter or override variables for this hook invocation').line('y')
            s.expect('TESTNOTIFY_TOKEN').line('NOTIFY-PTY-SECRET')
            s.expect('Apply notification settings and send the test notification').line('y')
        pty_case(t, 'pty-notify', 'notify set + hook env wizard + explicit test notification confirm', ['notify'], notify_env, drv_notify_set,
                 lambda rc, text: rc == 0 and argvlog(log)[0] == '--set-notify' and 'helper-pty' in argvlog(log) and 'NOTIFY-PTY-SECRET' not in text and notify_env_log.exists() and 'TESTNOTIFY_TOKEN=NOTIFY-PTY-SECRET' in notify_env_log.read_text())
        def drv_notify_hooks(s):
            s.expect('Notification action').line('hooks')
        pty_case(t, 'pty-notify', 'notify hook list interactive', ['notify'], env, drv_notify_hooks,
                 lambda rc, text: rc == 0 and 'testnotify' in text)

        account_cases = []
        def acc_status(s): s.expect('Account action').line('status')
        account_cases.append(('status', acc_status, lambda a, text: 'account_conf=' in text))
        def acc_register(s):
            s.expect('Account action').line('register'); s.expect('CA/server').line(''); s.expect('Account email').line('pty-account@example.com'); s.expect('EAB KID').line('')
        account_cases.append(('register', acc_register, lambda a, text: a[:3] == ['--register-account','--server','letsencrypt_test'] and 'pty-account@example.com' in a))
        def acc_update(s):
            s.expect('Account action').line('update'); s.expect('CA/server').line(''); s.expect('Account email').line('pty-update@example.com')
        account_cases.append(('update', acc_update, lambda a, text: a[:3] == ['--update-account','--server','letsencrypt_test'] and 'pty-update@example.com' in a))
        def acc_key(s):
            s.expect('Account action').line('key'); s.expect('CA/server').line(''); s.expect('Account key length').line('ec-384')
        account_cases.append(('key', acc_key, lambda a, text: '--update-account-key' in a and 'ec-384' in a))
        def acc_deactivate(s):
            s.expect('Account action').line('deactivate'); s.expect('CA/server').line(''); s.expect('Deactivate the ACME account').line('n')
        account_cases.append(('deactivate-cancel', acc_deactivate, lambda a, text: 'cancelled' in text and (not a or a[0] != '--deactivate-account')))
        for label, driver, check in account_cases:
            clear(log)
            pty_case(t, 'pty-account', 'account ' + label, ['account'], env, driver,
                     lambda rc, text, check=check: rc == 0 and check(argvlog(log), text))

        csr_cases = []
        def csr_show(s): s.expect('CSR/key action').line('show'); s.expect('CSR path').line('/tmp/pty.csr')
        csr_cases.append(('show', csr_show, lambda a: a == ['--show-csr','--csr','/tmp/pty.csr']))
        def csr_sign(s):
            s.expect('CSR/key action').line('sign'); s.expect('CSR path').line('/tmp/pty.csr'); s.expect('Validation mode').line('dns'); s.expect('DNS API').line('dns_namesilo')
        csr_cases.append(('sign', csr_sign, lambda a: a[:3] == ['--sign-csr','--csr','/tmp/pty.csr'] and '--dns' in a))
        def csr_create(s): s.expect('CSR/key action').line('create'); s.expect('Domains').line('a.test b.test'); s.expect('Key length').line('ec-384')
        csr_cases.append(('create', csr_create, lambda a: a[:3] == ['--create-csr','--keylength','ec-384'] and a.count('-d') == 2))
        def csr_domain(s): s.expect('CSR/key action').line('domain-key'); s.expect('Domain').line('a.test'); s.expect('Key length').line('2048')
        csr_cases.append(('domain-key', csr_domain, lambda a: a[0] == '--create-domain-key' and '2048' in a))
        def csr_account(s): s.expect('CSR/key action').line('account-key'); s.expect('Account key length').line('ec-384')
        csr_cases.append(('account-key', csr_account, lambda a: a == ['--create-account-key','--accountkeylength','ec-384']))
        for label, driver, check in csr_cases:
            clear(log)
            pty_case(t, 'pty-csr', 'csr ' + label, ['csr'], env, driver,
                     lambda rc, text, check=check: rc == 0 and check(argvlog(log)))

        clear(log)
        def exp_p12(s):
            s.expect('Export format').line('pkcs12'); s.expect('Certificate number').line('1'); s.expect('PFX password').line('PFX-PTY-SECRET')
        pty_case(t, 'pty-export', 'PKCS12 hidden password', ['export'], env, exp_p12,
                 lambda rc, text: rc == 0 and 'PFX-PTY-SECRET' not in text and '--to-pkcs12' in argvlog(log))
        clear(log)
        def exp_p8(s): s.expect('Export format').line('pkcs8'); s.expect('Certificate number').line('1')
        pty_case(t, 'pty-export', 'PKCS8 interactive', ['export'], env, exp_p8,
                 lambda rc, text: rc == 0 and argvlog(log)[0] == '--to-pkcs8')

        ca_cases = []
        def ca_default(s): s.expect('CA action').line('default'); s.expect('Default CA/server').line('letsencrypt')
        ca_cases.append(('default', ca_default, lambda a: a == ['--set-default-ca','--server','letsencrypt']))
        def ca_chain(s): s.expect('CA action').line('chain'); s.expect('CA/server').line('letsencrypt'); s.expect('Preferred chain').line('ISRGRootX1')
        ca_cases.append(('chain', ca_chain, lambda a: a[0] == '--set-default-chain' and 'ISRGRootX1' in a))
        def ca_profiles(s): s.expect('CA action').line('profiles'); s.expect('CA/server').line('letsencrypt')
        ca_cases.append(('profiles', ca_profiles, lambda a: a == ['--list-profiles','--server','letsencrypt']))
        def ca_persist(s):
            s.expect('CA action').line('dns-persist'); s.expect('Domains').line('a.test *.a.test'); s.expect('wildcard/subdomain').line('y'); s.expect('CA identity domain').line('ca.test'); s.expect('persistUntil').line('30')
        ca_cases.append(('dns-persist', ca_persist, lambda a: a[0] == '--make-dns-persist-value' and '--dns-persist-wildcard' in a and '30' in a))
        for label, driver, check in ca_cases:
            clear(log)
            pty_case(t, 'pty-ca', 'ca ' + label, ['ca'], env, driver,
                     lambda rc, text, check=check: rc == 0 and check(argvlog(log)))

        for kind, expected in [('dns','dns_namesilo'),('deploy','testdeploy'),('notify','testnotify')]:
            def drv_hooks(s, kind=kind): s.expect(MAIN_PROMPT).line('hooks'); s.expect('Hook type').line(kind)
            pty_case(t, 'pty-hooks', 'main hooks ' + kind, [], env, drv_hooks,
                     lambda rc, text, expected=expected: rc == 0 and expected in text)

        # Every non-DNS issue validation branch in real PTY mode.
        mode_cases = [
            ('webroot', lambda s: s.expect('Webroot path').line('/srv/www'), '--webroot'),
            ('standalone', lambda s: None, '--standalone'),
            ('alpn', lambda s: None, '--alpn'),
            ('stateless', lambda s: None, '--stateless'),
            ('apache', lambda s: None, '--apache'),
            ('nginx', lambda s: s.expect('Nginx configuration path').line('/etc/nginx/nginx.conf'), '--nginx'),
            ('dns-manual', lambda s: None, '--yes-I-know-dns-manual-mode-enough-go-ahead-please'),
            ('dns-persist', lambda s: None, '--dns-persist'),
        ]
        for mode, mode_driver, expected in mode_cases:
            clear(log)
            def drv_mode(s, mode=mode, mode_driver=mode_driver):
                s.expect('Domains:').line('mode.test'); s.expect('ACME Server').line(''); s.expect('Validation mode').line(mode); mode_driver(s); s.expect('Key length').line(''); s.expect('Output layout').line('none'); s.expect('Reload command').line(''); s.expect('Add other upstream parameters').line('n'); s.expect('Start issuing the certificate').line('y')
            pty_case(t, 'pty-issue-modes', 'interactive validation ' + mode, ['issue'], env, drv_mode,
                     lambda rc, text, expected=expected: rc == 0 and expected in argvlog(log))

        # ----- PTY guided issue: validation, each layout, advanced/cancel -----
        def drive_issue(s, layout, cert_name, advanced='n', confirm='y', bad_inputs=False):
            s.expect(MAIN_PROMPT).line('issue')
            s.expect('Domains:').line('*.pty1.test *.pty2.test')
            s.expect('Certificate mode').expect('Choose a number or command').line('merged')
            s.expect('ACME Server').line('')
            s.expect('Validation mode').line('')
            s.expect('DNS API').line('')
            if bad_inputs:
                s.expect('DNS wait in seconds').line('oops')
                s.expect('delay must be').expect('DNS wait in seconds').line('120')
                s.expect('Key length').line('bad')
                s.expect('unsupported keylength').expect('Key length').line('ec-256')
                s.expect('Output layout').line('bad')
                s.expect('output layout must').expect('Output layout').line(layout)
            else:
                s.expect('DNS wait in seconds').line('')
                s.expect('Key length').line('')
                s.expect('Output layout').line(layout)
            if layout != 'none':
                s.expect('Output root directory').line('')
                if bad_inputs:
                    s.expect('Certificate directory name').line('../bad')
                    s.expect('certificate name must').expect('Certificate directory name').line(cert_name)
                else:
                    s.expect('Certificate directory name').line(cert_name)
            s.expect('Reload command').line('')
            s.expect('Add other upstream parameters').line(advanced)
            if advanced == 'n':
                s.expect('Start issuing the certificate').line(confirm)

        for layout in ('full', 'minimal', 'nginx', 'none'):
            e = dict(env, ACME_OUTPUT_ROOT=td + '/pty-' + layout, MOCK_LOG=td + '/pty-' + layout + '.argv')
            clear(e['MOCK_LOG'])
            def drv(s, layout=layout):
                drive_issue(s, layout, 'pty-' + layout, bad_inputs=(layout == 'full'))
            def ass(rc, text, layout=layout, e=e):
                if rc != 0 or not pathlib.Path(e['MOCK_LOG']).exists():
                    return False
                if layout == 'none':
                    aa = argvlog(e['MOCK_LOG'])
                    return '--key-file' not in aa and '--fullchain-file' not in aa
                od = pathlib.Path(e['ACME_OUTPUT_ROOT']) / ('pty-' + layout)
                return (od / 'domains.txt').exists()
            pty_case(t, 'pty-issue-layouts', 'interactive issue layout ' + layout, [], e, drv, ass)

        # final cancel must not call upstream.
        e = dict(env, ACME_OUTPUT_ROOT=td + '/pty-cancel', MOCK_LOG=td + '/pty-cancel.argv')
        clear(e['MOCK_LOG'])
        def drv_cancel(s):
            drive_issue(s, 'none', 'unused', confirm='n')
        pty_case(t, 'pty-issue-confirm', 'interactive issue final cancel', [], e, drv_cancel,
                 lambda rc, text: rc == 0 and not pathlib.Path(e['MOCK_LOG']).exists() and 'cancelled' in text)

        # Advanced guided branch: invalid yes/no, managed option skip, flag addition, execute.
        e = dict(env, ACME_OUTPUT_ROOT=td + '/pty-advanced', MOCK_LOG=td + '/pty-advanced.argv')
        clear(e['MOCK_LOG'])
        force_i = idx(PARAMS, '--force')
        server_i = idx(PARAMS, '--server')
        def drv_adv(s):
            s.expect(MAIN_PROMPT).line('issue')
            s.expect('Domains:').line('*.advanced.test')
            s.expect('ACME Server').line('').expect('Validation mode').line('').expect('DNS API').line('').expect('DNS wait in seconds').line('')
            s.expect('Key length').line('').expect('Output layout').line('minimal')
            s.expect('Output root directory').line('').expect('Certificate directory name').line('advanced')
            s.expect('Reload command').line('')
            s.expect('Add other upstream parameters').line('maybe')
            s.expect('enter y or n').expect('Add other upstream parameters').line('y')
            s.expect('Upstream parameter >').line(server_i)
            s.expect('already managed by the issue wizard').expect('Upstream parameter >').line(force_i)
            s.expect('added:').expect('Upstream parameter >').line('done')
            s.expect('Start issuing the certificate').line('y')
        pty_case(t, 'pty-issue-advanced', 'guided advanced managed-skip + flag', [], e, drv_adv,
                 lambda rc, text: rc == 0 and '--force' in argvlog(e['MOCK_LOG']) and argvlog(e['MOCK_LOG']).count('--server') == 1)

        # Non-TTY full guided mode, final confirmation intentionally skipped because not a TTY.
        e = dict(env, ACME_OUTPUT_ROOT=td + '/pipe-guided', MOCK_LOG=td + '/pipe-guided.argv')
        data = 'issue\n*.pipe1.test *.pipe2.test\nmerged\n\n\n\n\n\nminimal\n\npipe-cert\n\nn\n'
        p = run_cli([], e, data)
        t.ok('non-tty-guided', p.returncode == 0 and '*.pipe2.test' in argvlog(e['MOCK_LOG']) and (pathlib.Path(e['ACME_OUTPUT_ROOT']) / 'pipe-cert' / 'domains.txt').exists(), 'no-args pipe guided issue')

        # ----- PTY config: defaults and all credential providers -----
        e = dict(env, ACME_WRAPPER_CONFIG=td + '/pty-defaults.ini')
        def drv_cfg_defaults(s):
            s.expect(MAIN_PROMPT).line('config')
            s.expect('Settings: defaults').line('bad')
            s.expect('enter defaults').expect('Settings: defaults').line('defaults')
            s.expect('ACME Server').line('')
            s.expect('DNS API').line('')
            s.expect('DNS wait in seconds').line('bad')
            s.expect('delay must').expect('DNS wait in seconds').line('33')
            s.expect('Key length').line('bad')
            s.expect('unsupported keylength').expect('Key length').line('ec-384')
            s.expect('Output root directory').line('')
            s.expect('Output layout').line('bad')
            s.expect('output layout must').expect('Output layout').line('minimal')
        pty_case(t, 'pty-config-defaults', 'interactive defaults config retries invalid fields', [], e, drv_cfg_defaults,
                 lambda rc, text: rc == 0 and pathlib.Path(e['ACME_WRAPPER_CONFIG']).exists() and 'dnssleep=33' in text and 'output_layout=minimal' in text)

        provider_cases = [
            ('dns_namesilo', ['NS-TTY-SECRET'], ['Namesilo_Key'], []),
            ('dns_cf', ['CF-TTY-SECRET'], ['CF_Token', 'CF_Account_ID'], ['2']),
            ('dns_gd', ['GD-TTY-KEY', 'GD-TTY-SECRET'], ['GD_Key', 'GD_Secret'], []),
        ]
        for provider, secrets, prompts, prefix_inputs in provider_cases:
            e = dict(env, ACME_ACCOUNT_CONF=td + '/pty-account-' + provider)
            def drv_provider(s, provider=provider, secrets=secrets, prompts=prompts, prefix_inputs=prefix_inputs):
                s.expect(MAIN_PROMPT).line('config')
                s.expect('Settings: defaults').line(provider)
                for item in prefix_inputs:
                    s.expect('Authentication method').line(item)
                values = list(secrets)
                if provider == 'dns_cf':
                    values.append('CF-TTY-ACCOUNT')
                for prompt, value in zip(prompts, values):
                    s.expect(prompt).line(value)
                if provider == 'dns_cf':
                    s.expect('CF_Zone_ID').line('')
            def ass_provider(rc, text, secrets=secrets, e=e):
                return rc == 0 and all(secret not in text for secret in secrets) and pathlib.Path(e['ACME_ACCOUNT_CONF']).exists()
            pty_case(t, 'pty-config-creds', 'interactive ' + provider + ' hidden secret', [], e, drv_provider, ass_provider)

        # Remaining provider schema branches in PTY mode.
        e = dict(env, ACME_ACCOUNT_CONF=td + '/pty-account-raw')
        def drv_raw(s):
            s.expect(MAIN_PROMPT).line('config')
            s.expect('Settings: defaults').line('dns_raw')
            s.expect('RAW_TOKEN').line('RAW-TTY-SECRET')
        pty_case(t, 'pty-config-provider-schemas', 'interactive raw-persistence provider', [], e, drv_raw,
                 lambda rc, text: rc == 0 and 'RAW-TTY-SECRET' not in text and 'RAW_TOKEN=' in pathlib.Path(e['ACME_ACCOUNT_CONF']).read_text())

        e = dict(env, ACME_ACCOUNT_CONF=td + '/pty-account-runtime')
        def drv_runtime(s):
            s.expect(MAIN_PROMPT).line('config')
            s.expect('Settings: defaults').line('dns_runtime')
        pty_case(t, 'pty-config-provider-schemas', 'interactive runtime-only provider', [], e, drv_runtime,
                 lambda rc, text: rc == 0 and 'runtime-only' in text and not pathlib.Path(e['ACME_ACCOUNT_CONF']).exists())

        e = dict(env, ACME_ACCOUNT_CONF=td + '/pty-account-legacy')
        def drv_legacy(s):
            s.expect(MAIN_PROMPT).line('config')
            s.expect('Settings: defaults').line('dns_legacy')
        pty_case(t, 'pty-config-provider-schemas', 'interactive legacy manual-schema provider', [], e, drv_legacy,
                 lambda rc, text: rc == 0 and 'structured Options metadata' in text)

        e = dict(env, ACME_ACCOUNT_CONF=td + '/pty-account-alt')
        def drv_alt(s):
            s.expect(MAIN_PROMPT).line('config')
            s.expect('Settings: defaults').line('dns_alt')
            s.expect('Authentication method').line('2')
            s.expect('ALT_USER').line('alt-user')
            s.expect('ALT_PASS').line('ALT-TTY-SECRET')
        pty_case(t, 'pty-config-provider-schemas', 'interactive OptionsAlt provider', [], e, drv_alt,
                 lambda rc, text: rc == 0 and 'ALT-TTY-SECRET' not in text and 'SAVED_ALT_PASS=' in pathlib.Path(e['ACME_ACCOUNT_CONF']).read_text())

        # Main native branch with all parameter editor branches.
        e = dict(env, MOCK_LOG=td + '/pty-native.argv')
        clear(e['MOCK_LOG'])
        info_i = idx(COMMANDS, '--info')
        force_i = idx(PARAMS, '--force')
        dns_i = idx(PARAMS, '--dnssleep')
        log_i = idx(PARAMS, '--log')
        secret_i = idx(PARAMS, '--eab-hmac-key')
        pre_i = idx(PARAMS, '--pre-hook')
        insecure_i = idx(PARAMS, '--output-insecure')
        secret = 'NATIVE-HMAC-SECRET'
        def drv_native(s):
            s.expect(MAIN_PROMPT).line('native')
            s.expect('Upstream command number').line('list')
            s.expect('Upstream command number').line('/info')
            s.expect('Upstream command number').line('x')
            s.expect('enter a number').expect('Upstream command number').line('999')
            s.expect('enter a number').expect('Upstream command number').line(info_i)
            s.expect('Upstream parameter >').line('list')
            s.expect('Upstream parameter >').line('/force')
            s.expect('Upstream parameter >').line('x')
            s.expect('enter a parameter number').expect('Upstream parameter >').line('999')
            s.expect('parameter number out of range').expect('Upstream parameter >').line(force_i)
            s.expect('added:').expect('Upstream parameter >').line(dns_i)
            s.expect('--dnssleep value').line('5')
            s.expect('added:').expect('Upstream parameter >').line(log_i)
            s.expect('--log value').line('')
            s.expect('added:').expect('Upstream parameter >').line(secret_i)
            s.expect('--eab-hmac-key:').line(secret)
            s.expect('added:').expect('Upstream parameter >').line(pre_i)
            s.expect('shell command').expect('--pre-hook value').line('echo safe-test')
            s.expect('added:').expect('Upstream parameter >').line(insecure_i)
            s.expect('secrets').expect('added:').expect('Upstream parameter >').line('done')
            s.expect('Execute the acme.sh command shown above').line('y')
        pty_case(t, 'pty-native', 'interactive native catalog/editor all input kinds', [], e, drv_native,
                 lambda rc, text: rc == 0 and secret not in text and '[hidden]' in text and secret in argvlog(e['MOCK_LOG']) and '--pre-hook' in argvlog(e['MOCK_LOG']))

        e = dict(env, MOCK_LOG=td + '/pty-native-cancel.argv')
        clear(e['MOCK_LOG'])
        def drv_native_cancel(s):
            s.expect(MAIN_PROMPT).line('native')
            s.expect('Upstream command number').line(info_i)
            s.expect('Upstream parameter >').line('done')
            s.expect('Execute the acme.sh command shown above').line('n')
        pty_case(t, 'pty-native', 'interactive native cancel', [], e, drv_native_cancel,
                 lambda rc, text: rc == 0 and not pathlib.Path(e['MOCK_LOG']).exists() and 'cancelled' in text)

        # ----- PTY terminal exits -----
        def drv_ctrl_c(s):
            s.expect(MAIN_PROMPT).ctrl_c()
        pty_case(t, 'pty-signals', 'Ctrl-C clean 130/no traceback', [], env, drv_ctrl_c,
                 lambda rc, text: rc == 130 and 'interrupted' in text and 'Traceback' not in text)

        def drv_ctrl_d(s):
            s.expect(MAIN_PROMPT).ctrl_d()
        pty_case(t, 'pty-signals', 'Ctrl-D clean 1/no traceback', [], env, drv_ctrl_d,
                 lambda rc, text: rc == 1 and 'input cancelled' in text and 'Traceback' not in text)

        # EOF in non-TTY prompt path.
        p = run_cli([], env, '')
        t.ok('non-tty-errors', p.returncode == 1 and 'input cancelled' in p.stderr, 'non-TTY EOF clean exit')

        return t.done()
    finally:
        if system_created:
            try:
                system_core.unlink()
            except OSError:
                pass
            try:
                system_dir.rmdir()
            except OSError:
                pass
        shutil.rmtree(td, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
