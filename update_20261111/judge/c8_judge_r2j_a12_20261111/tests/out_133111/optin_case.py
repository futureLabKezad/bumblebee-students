import json, sys, runpy
D = '/work/c8_judge_r2j_a12_20261111'
audit, o = json.loads(sys.argv[1]), sys.argv[2]
cfg = o + '/fake_mavros.yaml'; open(cfg, 'w').write('fcu_url: wrong\n')
audit.update(sim_gz_en_1=True, all_fcu_paths_guarded=True, no_hardware=True, raw_topics_verified=True, exclusive_profile_writer=True,
             mavros_config=cfg)
open(o + '/audit.json', 'w').write(json.dumps(audit))
sys.argv = ['vpe_profile_optin.py', '--sitl-opt-in', '--audit', o + '/audit.json', '--guard-directory', o, '--journal', o + '/j.json']
sys.path.insert(0, D + '/candidate/parameters')
try:
    runpy.run_path(D + '/candidate/parameters/vpe_profile_optin.py', run_name='__main__')
except RuntimeError as e:
    print(e)
