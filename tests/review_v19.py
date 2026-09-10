#!/usr/bin/env python3
"""Independent v1.9 regression: real public CLI/PTY, local fixtures only.

No DNS/CA calls or host service changes. Run with Python 3.7+.
This is a scenario inventory, not a claim of 100% source branch coverage.
"""
import ast
import configparser
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from adversarial import make_mock_home, base_env
from flow_matrix import PtyRun


class Checks:
    def __init__(self): self.rows = []
    def check(self, group, name, condition, detail=''):
        good = bool(condition)
        self.rows.append({'group': group, 'case': name, 'passed': good, 'detail': str(detail) if not good else ''})
        print(('PASS' if good else 'FAIL') + ' ' + group + '/' + name + (': ' + str(detail) if not good else ''), flush=True)
    def finish(self):
        if not self.rows: raise RuntimeError('zero tests are not success')
        out = os.environ.get('ACME_TEST_REPORT')
        if out: Path(out).write_text(json.dumps(self.rows, ensure_ascii=False, indent=2))
        for group in sorted({row['group'] for row in self.rows}):
            rows = [r for r in self.rows if r['group'] == group]
            print('GROUP {} {}/{}'.format(group, sum(r['passed'] for r in rows), len(rows)))
        failures = sum(not r['passed'] for r in self.rows)
        print('SUMMARY {}/{}'.format(len(self.rows) - failures, len(self.rows)))
        return bool(failures)


def call(args, env, data=None, exe=None):
    merged = os.environ.copy(); merged.update(env)
    return subprocess.run([str(exe or ROOT/'acme')] + args, input=data, universal_newlines=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged, timeout=20)


def argv(env):
    p = Path(env['MOCK_LOG'])
    return p.read_text().splitlines() if p.exists() else []


def clear(env):
    for key in ('MOCK_LOG', 'MOCK_HISTORY'):
        p = Path(env[key])
        if p.exists(): p.unlink()


def controlled_text(p): return p.stdout + p.stderr


def make_cert_fixture(td, env, keypath=''):
    listing=td/'certs.raw'; infos=td/'infos'; infos.mkdir(exist_ok=True)
    listing.write_text('Main_Domain|KeyLength|SAN_Domains|Profile|CA|Created|Renew\n'
                       'example.test|2048|*.example.test||LetsEncrypt|2026-01-01|2026-03-01\n'
                       'example.test|ec-256|*.example.test||LetsEncrypt|2026-01-01|2026-03-01\n')
    (infos/'example.test.info').write_text('Le_Domain=example.test\nLe_Alt=*.example.test\nLe_Webroot=dns_namesilo\nLe_RealKeyPath='+keypath+'\n')
    env.update(MOCK_CERT_LIST=str(listing), MOCK_CERT_INFO_DIR=str(infos))
    return listing


def pty_check(t, name, args, env, driver, validate):
    session = PtyRun(args, env)
    try:
        driver(session)
        rc, text = session.finish(timeout=8)
        t.check('flow', name, validate(rc, text), 'rc={} tail={!r}'.format(rc, text[-900:]))
    except Exception as exc:
        session.abort(); t.check('flow', name, False, exc)


def main():
    t=Checks(); source=(ROOT/'acme_cli.py').read_text()
    en=json.loads((ROOT/'locales/en.json').read_text()); zh=json.loads((ROOT/'locales/zh-TW.json').read_text())
    t.check('round3-i18n', 'catalog-key-parity', en.keys()==zh.keys())
    spec = importlib.util.spec_from_file_location('acme_core_v19', str(ROOT/'acme_cli.py'))
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
    redacted = core._redact_shortcut_args(['native','--password','TOP-SECRET','--eab-hmac-key=HMAC-SECRET','--server','letsencrypt'])
    t.check('round2-security','shortcut-central-secret-redaction', 'TOP-SECRET' not in redacted and 'HMAC-SECRET' not in redacted and redacted == ['native','--password','[hidden]','--eab-hmac-key=[hidden]','--server','letsencrypt'])
    fields=lambda x: [(f,s,c) for _,f,s,c in string.Formatter().parse(x) if f is not None]
    bad=[key for key in en if fields(key)!=fields(en[key]) or fields(key)!=fields(zh[key])]
    t.check('round3-i18n','format-placeholder-parity',not bad,bad)
    tree=ast.parse(source)
    literal_messages={n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str)}
    t.check('round3-i18n','all-literal-messages-in-catalog',not literal_messages-en.keys(),literal_messages-en.keys())
    shadows=[n.lineno for n in ast.walk(tree) if isinstance(n,ast.Name) and n.id=='_' and isinstance(n.ctx,ast.Store)]
    t.check('round2-security','no-translation-function-shadowing',not shadows,shadows)
    subproc_text=[n.lineno for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and any(k.arg=='text' for k in n.keywords)]
    t.check('round3-i18n','python36-subprocess-contract',not subproc_text,subproc_text)
    try: ast.parse(source, feature_version=(3,6)); syntax=True
    except (ValueError,SyntaxError): syntax=False
    t.check('round3-i18n','python36-grammar-only',syntax,'This is not a Python 3.6 runtime test')

    with tempfile.TemporaryDirectory(prefix='acme-v18-review-') as tmp:
        td=Path(tmp); home,exe=make_mock_home(td); env=base_env(td,exe)
        env['HOME']=str(td/'user'); Path(env['HOME']).mkdir()
        for lang in ('en','zh-TW'):
            e=dict(env,ACME_HELPER_LANG=lang)
            p=call(['--help'],e)
            t.check('round1-correctness','help-'+lang,p.returncode==0 and 'acme quick' in p.stderr and 'acme certs' in p.stderr)
            p=call(['-format','none','example.test *.example.test'],e)
            expected=['--issue','--server','letsencrypt','--keylength','ec-256','--dns','dns_namesilo','--dnssleep','120','-d','example.test','-d','*.example.test']
            t.check('round1-correctness','language-does-not-change-argv-'+lang,p.returncode==0 and argv(e)==expected,controlled_text(p))
            if lang=='en': t.check('round3-i18n','english-controlled-issue-no-cjk',not re.search('[\u4e00-\u9fff]',controlled_text(p)))
            else: t.check('round3-i18n','traditional-chinese-issue-present',bool(re.search('[\u4e00-\u9fff]',p.stderr)))
            secret="L10N-'quoted-$(touch /tmp/ACME_NOT_EXECUTED)"
            p=call(['config','dns_namesilo'],e,secret+'\n')
            t.check('round2-security','secret-not-translated-or-echoed-'+lang,p.returncode==0 and secret not in controlled_text(p) and 'L10N-' in Path(e['ACME_ACCOUNT_CONF']).read_text())
            p=call(['native','--future-param','untranslated-token','--lang','xx'],e)
            t.check('round3-i18n','native-options-preserved-'+lang,p.returncode==0 and argv(e)==['--future-param','untranslated-token','--lang','xx'])
        # Verify the actual child environment bridge, not only an argv mock.
        capture_home=td/'context-home';capture_home.mkdir();capture=capture_home/'acme.sh'
        capture.write_text('#!/bin/sh\nprintf "work=%s\nconfig=%s\naccount=%s\n" "$LE_WORKING_DIR" "${LE_CONFIG_HOME:-}" "$ACCOUNT_CONF_PATH"\n')
        capture.chmod(0o755)
        context_env=dict(env,ACME_SH_BIN=str(capture),ACME_ACCOUNT_CONF=str(td/'custom account.conf'))
        context_env.pop('LE_WORKING_DIR',None);context_env.pop('LE_CONFIG_HOME',None)
        p=call(['native','--info'],context_env)
        t.check('round1-correctness','actual-child-custom-account-path',p.returncode==0 and 'account='+str(td/'custom account.conf') in p.stdout and 'work='+str(capture_home) in p.stdout,controlled_text(p))
        context_env.update(LE_WORKING_DIR=str(td/'explicit-working'),LE_CONFIG_HOME=str(td/'explicit-config'))
        p=call(['native','--info'],context_env)
        t.check('round1-correctness','explicit-upstream-homes-preserved',p.returncode==0 and 'work='+str(td/'explicit-working') in p.stdout and 'config='+str(td/'explicit-config') in p.stdout)
        # A copied program can also expose its working/config home through status.
        context_env.pop('ACME_ACCOUNT_CONF');context_env['ACME_SH_BIN']=str(exe)
        Path(context_env['LE_CONFIG_HOME']).mkdir();(Path(context_env['LE_CONFIG_HOME'])/'account.conf').write_text("SAVED_Namesilo_Key='CONFIG-HOME-SECRET'\n")
        p=call(['status','dns_namesilo'],context_env)
        t.check('round1-correctness','configuration-reader-honors-upstream-config-home',p.returncode==0 and 'dns_namesilo=configured' in p.stdout and 'CONFIG-HOME-SECRET' not in controlled_text(p))
        # Configuration precedence and data-preserving language update.
        cfg=Path(env['ACME_WRAPPER_CONFIG']); cfg.write_text('[defaults]\nserver=letsencrypt_test\n[custom]\nkeep=value\n')
        p=call(['language','en'],dict(env,ACME_HELPER_LANG='zh-TW'))
        parsed=configparser.RawConfigParser();parsed.read(str(cfg))
        t.check('round1-correctness','language-persists-without-dropping-settings',p.returncode==0 and parsed.get('defaults','server')=='letsencrypt_test' and parsed.get('custom','keep')=='value' and parsed.get('ui','language')=='en')
        noenv=dict(env);noenv.pop('ACME_HELPER_LANG',None)
        p=call(['language'],noenv); t.check('round1-correctness','saved-language-used',p.stdout.strip()=='language=en')
        p=call(['--lang','zh-TW','language'],dict(env,ACME_HELPER_LANG='en'));t.check('round1-correctness','cli-language-wins',p.stdout.strip()=='language=zh-TW')
        p=call(['language'],dict(env,ACME_HELPER_LANG='zh-TW'));t.check('round1-correctness','environment-language-wins',p.stdout.strip()=='language=zh-TW')
        p=call(['account','register','--email','ops@example.test'],env);t.check('round1-correctness','account-uses-saved-ca',p.returncode==0 and 'letsencrypt_test' in argv(env))
        p=call(['csr','sign','/tmp/example.csr','--dns','dns_namesilo'],env);t.check('round1-correctness','csr-uses-saved-ca',p.returncode==0 and 'letsencrypt_test' in argv(env))
        cfg.unlink()
        # Every helper command can show offline help. No upstream access is necessary.
        names=['quick','issue','install','uninstall','certs','deploy','notify','account','csr','export','ca','hooks','cron','providers','config','status','defaults','language','version','versions','update','switch','rollback']
        missing=dict(env,ACME_SH_BIN=str(td/'not-installed'))
        for name in names:
            p=call([name,'--help'],missing)
            t.check('flow','offline-help-'+name,p.returncode==0 and ('Usage:' in p.stderr or 'acme' in p.stderr))
        p=call(['help','certs'],missing);t.check('flow','help-command-alias',p.returncode==0 and 'certs' in p.stderr)
        clear(env)
        for lang in ('en','zh-TW','../../evil','fr',''):
            if lang in ('en','zh-TW'): continue
            p=call(['--lang',lang,'language'],env)
            t.check('round2-security','invalid-language-'+repr(lang),p.returncode==2 and not Path(env['MOCK_LOG']).exists(),controlled_text(p))
        # Empty saved values are not configured; environment credentials may be used.
        Path(env['ACME_ACCOUNT_CONF']).write_text("SAVED_Namesilo_Key=''\n")
        p=call(['status','dns_namesilo'],env)
        t.check('round2-security','empty-key-is-not-configured',p.returncode==0 and 'dns_namesilo=configured' not in p.stdout)
        p=call(['status','dns_namesilo'],dict(env,Namesilo_Key='environment-only'))
        t.check('round1-correctness','environment-key-recognized',p.returncode==0 and 'dns_namesilo=configured' in p.stdout and 'environment-only' not in controlled_text(p))
        # No switch to a different RSA/ECC identity through a second lookup.
        listing=make_cert_fixture(td,env)
        for index,ecc in [('1',False),('2',True)]:
            p=call(['certs','deploy',index,'--hook','testdeploy','--yes'],env)
            t.check('round1-correctness','selected-identity-deploy-'+index,p.returncode==0 and ('--ecc' in argv(env))==ecc,controlled_text(p))
        for args in [['certs','renew-all','--reason','1'],['certs','renew-all','--hook','testdeploy'],['-format','none','example.test','--','--server=zerossl']]:
            clear(env);p=call(args,env)
            t.check('round2-security','reject-inapplicable-'+args[-1],p.returncode==2 and '--renew-all' not in argv(env) and '--issue' not in argv(env))
        listing.write_text(listing.read_text()+'malformed-row\n')
        clear(env);p=call(['certs','list'],env);t.check('round2-security','malformed-row-not-silently-skipped',p.returncode==2 and 'incomplete inventory' in p.stderr)
        # Output collision refuses before execution while preserving existing contents.
        key=td/'out'/'example.test'/'key.pem';key.parent.mkdir(parents=True);key.write_text('DO-NOT-OVERWRITE')
        make_cert_fixture(td,env,str(key)); clear(env)
        p=call(['-keylength','ec-256','example.test *.example.test'],env)
        t.check('round2-security','saved-output-collision-blocked',p.returncode==2 and '--issue' not in argv(env) and key.read_text()=='DO-NOT-OVERWRITE',controlled_text(p))
        env.pop('MOCK_CERT_LIST');env.pop('MOCK_CERT_INFO_DIR')
        # Cron detection is scoped to the actual installation, not a substring.
        fake=td/'bin';fake.mkdir(); crontab=fake/'crontab';cronfile=td/'crontab.txt'
        crontab.write_text('#!/bin/sh\ncat "$TEST_CRONTAB"\n');crontab.chmod(0o755)
        ce=dict(env,PATH=str(fake)+os.pathsep+os.environ['PATH'],TEST_CRONTAB=str(cronfile))
        for name,line,expected in [
            ('other-home','0 0 * * * /opt/other/acme.sh --cron','disabled'),
            ('comment','# 0 0 * * * '+str(exe)+' --cron','disabled'),
            ('same-home','0 0 * * * "'+str(exe)+'" --cron --home "'+str(home)+'"','enabled')]:
            cronfile.write_text(line+'\n');p=call(['cron','status'],ce)
            t.check('round2-security','cron-'+name,p.returncode==0 and 'cron='+expected in p.stdout)
        # Failed download containing executable partial bytes must not execute.
        marker=td/'partial-executed';curl=fake/'curl'
        curl.write_text('#!/bin/sh\nprintf \'touch "%s"\\n\' "$TEST_MARKER"\nexit 22\n');curl.chmod(0o755)
        ie=dict(env,PATH=str(fake)+os.pathsep+os.environ['PATH'],TEST_MARKER=str(marker));ie.pop('ACME_SH_BIN')
        p=call(['install','--no-profile'],ie)
        t.check('round2-security','partial-download-not-executed',p.returncode==22 and not marker.exists(),controlled_text(p))
        # Catalog removal is genuine ablation: core functions still operate in English.
        copy=td/'no-catalog';copy.mkdir();shutil.copy2(str(ROOT/'acme'),str(copy/'acme'));shutil.copy2(str(ROOT/'acme_cli.py'),str(copy/'acme_cli.py'))
        p=call(['--help'],dict(env,ACME_HELPER_LANG='zh-TW'),exe=copy/'acme')
        t.check('ablation','remove-catalog-safe-english-fallback',p.returncode==0 and 'catalog unavailable' in p.stderr and 'acme quick' in p.stderr)
        p=call(['native','--info'],dict(env,ACME_HELPER_LANG='zh-TW'),exe=copy/'acme')
        t.check('ablation','remove-catalog-native-argv-unchanged',p.returncode==0)
        p=call(['-format','none','fallback.test'],dict(env,ACME_HELPER_LANG='zh-TW'),exe=copy/'acme')
        t.check('ablation','remove-catalog-issue-works',p.returncode==0 and 'fallback.test' in argv(env))
        # Identity catalogs are optional; corrupted translation data is not executable.
        (copy/'locales').mkdir();(copy/'locales'/'zh-TW.json').write_text('not-json $(touch pwned)')
        p=call(['--help'],dict(env,ACME_HELPER_LANG='zh-TW'),exe=copy/'acme')
        t.check('round3-i18n','invalid-json-falls-back',p.returncode==0 and 'catalog unavailable' in p.stderr)
        # Existing CLI does not depend on the new quick menu.
        p=call(['issue','-format','none','expert.test'],env)
        t.check('ablation','quick-menu-not-required-for-expert-cli',p.returncode==0 and 'expert.test' in argv(env))
        t.check('round1-correctness','direct-cli-does-not-print-guided-shortcut',p.returncode==0 and 'CLI shortcut for next time:' not in controlled_text(p) and '下次可直接執行：' not in controlled_text(p))
        # Mutations demonstrate that two retained safeguards are necessary.
        for name,old,new,command,setup,oracle in [
            ('nonempty-credential-check', 'return len(values) == 1 and bool(values[0])', 'return len(values) == 1', ['status','dns_namesilo'], lambda:Path(env['ACME_ACCOUNT_CONF']).write_text("SAVED_Namesilo_Key=''\n"), lambda p:'dns_namesilo=configured' in p.stdout),
            ('complete-download-check','if fetched.returncode != 0:', 'if False:', ['install','--no-profile'],lambda:None,lambda p:marker.exists())]:
            mutant=td/('mutant-'+name);mutant.mkdir();shutil.copy2(str(ROOT/'acme'),str(mutant/'acme'))
            assert old in source
            (mutant/'acme_cli.py').write_text(source.replace(old,new,1));setup()
            p=call(command,ie if name=='complete-download-check' else env,exe=mutant/'acme')
            t.check('ablation','removing-'+name+'-causes-regression',oracle(p),controlled_text(p))
        # PTY bilingual task navigation, state changes, cancel, actual input editing.
        for lang in ('en','zh-TW'):
            e=dict(env,ACME_HELPER_LANG=lang)
            messages=en if lang=='en' else zh
            ui=lambda key:messages.get(key,key)
            main_prompt=ui('Action (number or command)')
            chooser=ui('Choose a number or command; :back returns to the main menu')
            def leave(s,mp=main_prompt):s.expect(mp).line('0')
            pty_check(t,'menu-exit-'+lang,[],e,leave,lambda rc,out:rc==0)
            def back(s,mp=main_prompt,ch=chooser):
                s.expect(mp).line('6');s.expect(ch).line(':back');s.expect(mp).line('0')
            pty_check(t,'advanced-back-'+lang,[],e,back,lambda rc,out:rc==0)
            def status(s,mp=main_prompt,ch=chooser):
                s.expect(mp).line('4');s.expect(ch).line('1');s.expect(ui('Scheduling action')).expect(ch).line('status');s.expect(mp).line('0')
            pty_check(t,'numeric-scheduling-'+lang,[],e,status,lambda rc,out:rc==0 and 'cron=' in out and 'acme cron status' in out and ui('CLI shortcut for next time:') in out)
            def quick_cancel(s):
                s.expect(ui('Domains, separated by spaces')).line('cancel.test')
                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('')
                s.expect(ui('Configure this DNS provider now?')).line('n')
                s.expect(ui('Start issuing this certificate?')).line('n')
            clear(e)
            pty_check(t,'quick-cancel-'+lang,['quick'],e,quick_cancel,lambda rc,out:rc==0 and '--issue' not in argv(e) and ui('CLI shortcut for next time:') in out and ('acme issue --server letsencrypt --keylength ec-256 --dns dns_namesilo --dnssleep 120 --output-layout minimal --output-root ' + e['ACME_OUTPUT_ROOT'] + ' --cert-name cancel.test cancel.test') in out)
            def quick_ok(s):
                s.expect(ui('Domains, separated by spaces')).line('quick.test *.quick.test')
                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('/namesilo')
                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('1')
                s.expect(ui('Configure this DNS provider now?')).line('y')
                s.expect('Namesilo_Key').line('PTY-HIDDEN-KEY')
                s.expect(ui('Start issuing this certificate?')).line('y')
            clear(e);Path(e['ACME_ACCOUNT_CONF']).write_text("SAVED_Namesilo_Key=''\n")
            pty_check(t,'quick-search-config-issue-'+lang,['quick'],e,quick_ok,lambda rc,out:rc==0 and 'PTY-HIDDEN-KEY' not in out and '--issue' in argv(e) and '*.quick.test' in argv(e) and ui('CLI shortcut for next time:') in out and ("acme issue --server letsencrypt --keylength ec-256 --dns dns_namesilo --dnssleep 120 --output-layout minimal --output-root " + e['ACME_OUTPUT_ROOT'] + " --cert-name quick.test 'quick.test *.quick.test'") in out)
            Path(e['ACME_ACCOUNT_CONF']).write_text("SAVED_Namesilo_Key=''\n")
            def ctrl_c(s,mp=main_prompt):s.expect(mp);time.sleep(.08);s.ctrl_c()
            pty_check(t,'ctrl-c-'+lang,[],e,ctrl_c,lambda rc,out:rc==130 and 'Traceback' not in out)
            def ctrl_d(s,mp=main_prompt):s.expect(mp);time.sleep(.08);s.ctrl_d()
            pty_check(t,'ctrl-d-'+lang,[],e,ctrl_d,lambda rc,out:rc==1 and 'Traceback' not in out)
            def retry(s,mp=main_prompt):s.expect(mp).line('invalid');s.expect(mp).line('0')
            pty_check(t,'invalid-menu-retry-'+lang,[],e,retry,lambda rc,out:rc==0)
        # Read-only guided actions also expose exact shortcuts for fast operator reuse.
        e=dict(env,ACME_HELPER_LANG='en')
        def guided_group_action(group, action, expected, extra=None):
            def driver(session):
                session.expect('Action (number or command)').line(group)
                session.expect('Choose a number or command; :back returns to the main menu').line(action)
                if extra:
                    prompt, value = extra
                    session.expect(prompt).line(value)
                session.expect('CLI shortcut for next time:').expect(expected)
                session.expect('Action (number or command)').line('0')
            return driver
        for name,group,action,expected,extra in [
            ('shortcut-version-read','5','version','acme version --full',None),
            ('shortcut-versions-read','5','versions','acme versions',None),
            ('shortcut-defaults-read','7','defaults','acme defaults',None),
            ('shortcut-status-read','7','status','acme status',None),
            ('shortcut-providers-read','7','providers','acme providers cloud',('Search providers (Enter=all):','cloud')),
            ('shortcut-hooks-read','6','hooks','acme hooks deploy',('Hook type','deploy')),
        ]:
            pty_check(t,name,[],e,guided_group_action(group,action,expected,extra),lambda rc,out,expected=expected: rc==0 and expected in out)

        # Shortcut previews are copyable but never include secret values or destructive --yes bypasses.
        e=dict(env,ACME_HELPER_LANG='en')
        clear(e)
        def uninstall_shortcut(s):
            s.expect('Uninstall acme.sh and its upstream cron job').line('n')
        pty_check(t,'shortcut-uninstall-no-auto-yes',['uninstall'],e,uninstall_shortcut,
                  lambda rc,out:rc==0 and 'CLI shortcut for next time:' in out and 'acme uninstall' in out and 'acme uninstall --yes' not in out and '--uninstall' not in argv(e))

        clear(e)
        def account_eab_shortcut(s):
            s.expect('Account action').line('register')
            s.expect('CA/server').line('')
            s.expect('Account email').line('ops@example.test')
            s.expect('EAB KID').line('eab-kid-1')
            s.expect('EAB HMAC key').line('EAB-PTY-SECRET')
        pty_check(t,'shortcut-account-eab-secret-safe',['account'],e,account_eab_shortcut,
                  lambda rc,out:rc==0 and 'EAB-PTY-SECRET' not in out and 'acme account register --server letsencrypt --email ops@example.test --eab-kid eab-kid-1 --eab-hmac-stdin' in out and '--eab-hmac-key' in argv(e))

        # Readline interaction: deletion, arrow keys and UTF-8 input are not shell parsing.
        e=dict(env,ACME_HELPER_LANG='en')
        for label,encoded in [('del','junk\x7f\x7f\x7f\x7f0'),('backspace','junk\x08\x08\x08\x080'),('arrows','0x\x1b[D\x1b[3~'),('utf8','\u6e2c\u8a66\x7f\x7f0')]:
            def edit(s,value=encoded):
                s.expect('Action (number or command)');time.sleep(.08);s.line(value)
            pty_check(t,'editing-'+label,[],e,edit,lambda rc,out:rc==0 and 'Traceback' not in out)
        # :back is navigation only for normal fields, never for a secret value.
        Path(e['ACME_ACCOUNT_CONF']).write_text("SAVED_Namesilo_Key=''\n")
        def secret_back(s):
            s.expect('Namesilo_Key');time.sleep(.05);s.line(':back')
        pty_check(t,'secret-back-is-data',['config','dns_namesilo'],e,secret_back,lambda rc,out:rc==0 and ':back' not in out and ':back' in Path(e['ACME_ACCOUNT_CONF']).read_text())
        # English-to-Chinese switch is visible on the next loop iteration.
        language_env=dict(env);language_env.pop('ACME_HELPER_LANG',None)
        Path(language_env['ACME_WRAPPER_CONFIG']).write_text('[ui]\nlanguage=en\n')
        def switch_language(s):
            s.expect('Action (number or command)').line('7')
            s.expect('Choose a number or command').line('language')
            s.expect('Choose a number or command').line('1')
            s.expect(zh['Action (number or command)']).line('0')
        pty_check(t,'language-change-refreshes-menu',[],language_env,switch_language,lambda rc,out:rc==0 and zh['Action (number or command)'] in out)
        # Native output is not run through the message translator.
        output_home=td/'output-home';output_home.mkdir();output_prog=output_home/'acme.sh'
        output_prog.write_text("#!/bin/sh\nprintf 'UPSTREAM-RAW: Certificate issued successfully.\\n'\n");output_prog.chmod(0o755)
        p=call(['native','--info'],dict(env,ACME_SH_BIN=str(output_prog),ACME_HELPER_LANG='zh-TW'))
        t.check('round3-i18n','upstream-output-not-translated',p.stdout.strip()=='UPSTREAM-RAW: Certificate issued successfully.')
        # Real installation includes catalogs under a custom prefix.
        prefix=td/'install prefix';ie2=os.environ.copy();ie2.update(env);ie2['PREFIX']=str(prefix)
        q=subprocess.run([str(ROOT/'install.sh')],env=ie2,universal_newlines=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        p=call(['--help'],dict(env,ACME_HELPER_LANG='zh-TW'),exe=prefix/'bin'/'acme') if q.returncode==0 else q
        t.check('flow','custom-prefix-install-includes-i18n',q.returncode==0 and (prefix/'lib/acme/locales/zh-TW.json').is_file() and 'catalog unavailable' not in controlled_text(p) and bool(re.search('[\u4e00-\u9fff]',p.stderr)),controlled_text(q))
    return t.finish()


if __name__=='__main__': raise SystemExit(main())
