#!/usr/bin/env python3
"""patch_review_s1_s2.py - review of the final r2h (REVIEW_r2h_final.md), SHOULD 1-3; tests and notes only, no image
behaviour changes. S1: test_pins_r3 also pins the content of the declared parts (sha256 of ast.dump, Python 3.12 =
Jazzy). S2: test_r2h_vpe gets a hold-length test with a control (hold 0.05 s must fail it). S3: the candidate's
DIFF_r2h_vs_r2g.txt and TSV are kept in notes/prev_r2h_candidate. Each anchor must match exactly once.
Usage: python3 -I patch_review_s1_s2.py"""
import shutil
import sys
from pathlib import Path

D = Path('/work/fixed_image_r2h_20261110')
C = Path('/work/fixed_image_r2h_candidate_20261110')
DIGESTS = {
    'VpeFix.__init__': 'f7bfb962bb3258f8cb5b3f31730a61d4cf9a639c1a379eff14d721b979a5ea4b',
    'VpeFix._maybe_reseed': 'e35321f44f3fe1551a36904cd38ed92ab3a3b33c302dae1e6395c9fe6bdcd6a3',
    'VpeFix._reentry_pose': 'e2fd39815ef72dcd295852c8cc82bf8ad153b2bf7b033db6d7cbb717059ef9a5',
    'VpeFix._single_marker_fresh': 'fd8536f34866873c7ceef75e5499c2cf4ea2dc1b532e6077a9dab8d92095db82',
    'VpeFix.aruco_map_callback': '7da3d38a55f618ada8533235ebe8ca61225fc8597ef9279023a000948a0fe1fb',
    'VpeFix.markers_used_callback': '585476054dae507605de71b94e239df363f7905fcfc958006c8b0ff4b129dfe7',
    'VpeFix.publish_timer': '3c734041146f4b823a232b65f989082377effe054bb836ac371b1d5d697813ff',
    'VpeFix.yaw_locked_callback': '8cd89c71284a81e4ba0ad7a9e35b0556a81c747dca96f0351230696f7e812852',
    'const _REENTRY_GAP': 'b2c45f7fe015c16e902eaa49d31812d3cfe6d1f34a388beac50ffb8ec2518385',
    'const _REENTRY_HOLD': '58547221ee78862df0bb04b94411232b1c0ac1918af7004d5c66795b18b1b8b8',
    'const _REENTRY_MAX_WAIT': 'b2c45f7fe015c16e902eaa49d31812d3cfe6d1f34a388beac50ffb8ec2518385',
    'const _REENTRY_N': '9084d9e7883c1863a636c76e7bbb39dcab454c4a629ddb9b02e896f4c3ea1c29',
}


def edit(rel, old, new):
    p = D / rel
    t = p.read_text()
    if t.count(old) != 1:
        sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
    p.write_text(t.replace(old, new))
    print('edited', rel)


R3 = 'src/bumblebee/test/vpe_fix_h2_r2/tests_r3/test_pins_r3.py'
edit(R3, "Env: PIN_TARGET (file under test)",
     "Content (review of the final, S1): the declared parts are also pinned to the accepted final r2h (sha256 of their\n"
     "ast.dump; ast.dump is stable within a Python minor version: 3.12 = ROS 2 Jazzy, PC and drone). A change of a declared\n"
     "part therefore needs a new pin round, like any other part.\n\n"
     "Env: PIN_TARGET (file under test)")
edit(R3, "REENTRY = {'_REENTRY_GAP': 0.3",
     "DIGESTS = {\n" + ''.join("    %r: %r,\n" % kv for kv in sorted(DIGESTS.items())) + "}\n"
     "REENTRY = {'_REENTRY_GAP': 0.3")
edit(R3, "    def test_r3_aruco_map_callback_one_added_statement(self):",
     "    def test_r3_declared_parts_are_the_accepted_final(self):\n"
     "        self.assertEqual(set(DIGESTS), CHANGED | ADDED)\n"
     "        b = parts(tree(TARGET))\n"
     "        for k, v in DIGESTS.items():\n"
     "            self.assertEqual(hashlib.sha256(b[k].encode()).hexdigest(), v, k)\n\n"
     "    def test_r3_aruco_map_callback_one_added_statement(self):")

VPE_T = 'test/test_r2h_vpe.py'
edit(VPE_T, "\n\nclass B2TwoPoses(unittest.TestCase):",
     "\n\nclass B2Hold(unittest.TestCase):\n"
     "    \"\"\"review of the final (S2): the medoid is published for _REENTRY_HOLD = 0.5 s after the first sample, then the\n"
     "    latest pose. After the pause every 3rd pose is +0.03 (the medoid of the last 3 is then 0.0, not the latest).\n"
     "    Control: the same scenario with a 0.05 s hold fails the bound.\"\"\"\n"
     "\n"
     "    @staticmethod\n"
     "    def last_differing(mod):\n"
     "        frames = []\n"
     "\n"
     "        def det(t):\n"
     "            if t < 2.1:\n"
     "                return 2, (0.0, 0.0, 1.0)\n"
     "            if t < 3.1:\n"
     "                return 0, None\n"
     "            x = 0.03 if len(frames) % 3 == 2 else 0.0\n"
     "            frames.append((t, x))\n"
     "            return 2, (x, 0.0, 1.0)\n"
     "        s = Sim(mod, det)\n"
     "        s.run(5.0)\n"
     "        after = s.sent(after=frames[0][0])\n"
     "        t1 = after[0][0]\n"
     "        latest = lambda t: [x for tf, x in frames if tf < t][-1]       # timers fire before a frame at the same time\n"
     "        differ = [t for t, m in after if abs(m.pose.pose.position.x - latest(t)) > 1e-9]\n"
     "        return t1, differ\n"
     "\n"
     "    def test_hold_is_half_a_second(self):\n"
     "        t1, differ = self.last_differing(R2H)\n"
     "        self.assertTrue(differ)\n"
     "        self.assertGreaterEqual(max(differ), t1 + 0.3)\n"
     "        self.assertLess(max(differ), t1 + R2H._REENTRY_HOLD + 1e-6)\n"
     "        short = B.load(str(R2H_VPE), 'vpe_fix_r2h_hold_control')\n"
     "        short._REENTRY_HOLD = 0.05                                       # control only (module copy)\n"
     "        ct1, cdiffer = self.last_differing(short)\n"
     "        self.assertTrue(not cdiffer or max(cdiffer) < ct1 + 0.1, (ct1, cdiffer))\n"
     "\n"
     "\nclass B2TwoPoses(unittest.TestCase):")

P = D / 'notes/prev_r2h_candidate'
for f in ('notes/DIFF_r2h_vs_r2g.txt', 'image_manifest_r2.tsv'):
    dst = P / Path(f).name
    if not dst.exists():
        shutil.copy2(C / f, dst)
        print('kept', dst)
