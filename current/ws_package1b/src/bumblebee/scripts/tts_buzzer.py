#!/usr/bin/env python3
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Convert text to a PX4 PLAY_TUNE_V2 QBASIC string via espeak-ng phonemes.

The buzzer is monophonic so this is an intentional low-fi caricature of
speech ("Microsoft Talk It" / Crystal Castles aesthetic), not real TTS.
"""

import shutil
import subprocess
import sys

ALLOWED_LANGS = {'en', 'en-us', 'en-gb', 'ru', 'de', 'fr', 'es'}
MAX_TUNE = 230
MAX_TEXT = 400

# Vowels: emit a clear note in the upper register.
_VOWEL_NOTE = {
    'i': 'E', 'I': 'E',
    'e': 'D', 'E': 'D',
    'a': 'C', '&': 'C', 'A': 'C',
    '@': 'A', 'V': 'A', '3': 'A',
    'O': 'F', 'o': 'F',
    'U': 'G', 'u': 'G',
    'Y': 'B',
}

# Vowel digraphs (diphthongs etc.) → multi-note slides.
_DIGRAPH_NOTE = {
    'aI': ['C', 'E'],
    'aU': ['C', 'G'],
    'OI': ['F', 'E'],
    'eI': ['D', 'E'],
    'oU': ['F', 'G'],
}

# Voiced consonants → short blip note. None = silence.
_CONSONANT_BLIP = {
    'b': 'C', 'd': 'D', 'g': 'G',
    'm': 'C', 'n': 'D', 'N': 'E',
    'l': 'E', 'r': 'D',
    'v': 'C', 'z': 'D', 'Z': 'E', 'D': 'C',
    'j': 'A', 'w': 'G',
    'h': None,
    'p': None, 't': None, 'k': None,
    'f': None, 's': None, 'S': None, 'T': None,
}

_AFFRICATE = {
    'tS': None,
    'dZ': ['D'],
}


def _run_espeak(text, lang):
    if not shutil.which('espeak-ng'):
        return ''
    if lang not in ALLOWED_LANGS:
        lang = 'en'
    try:
        r = subprocess.run(
            ['espeak-ng', '-q', '-x', '-v', lang],
            input=text, capture_output=True, text=True, timeout=3,
        )
    except Exception:
        return ''
    if r.returncode != 0:
        return ''
    return r.stdout.strip()


def _naive_fallback(text):
    cycle = ['C', 'E', 'G']
    parts = ['MFT180O5L16']
    idx = 0
    for ch in text:
        if sum(len(p) for p in parts) >= MAX_TUNE - 2:
            break
        if ch.isspace():
            parts.append('P8')
        elif ch.lower() in 'aeiouyаеёиоуыэюя':
            parts.append(cycle[idx % 3])
            idx += 1
    tune = ''.join(parts)
    if len(tune) > MAX_TUNE:
        tune = tune[:MAX_TUNE]
    return tune


def tts_to_tune(text, lang='en'):
    text = (text or '').strip()
    if not text:
        raise ValueError('empty text')
    text = text[:MAX_TEXT]
    lang = (lang or 'en').strip().lower()
    if lang not in ALLOWED_LANGS:
        lang = 'en'

    phonemes = _run_espeak(text, lang)
    if not phonemes:
        return _naive_fallback(text), ''

    parts = ['MFT180O5L16']
    cur_len = 16
    pending_stress = False
    last_was_note = False
    i = 0
    n = len(phonemes)

    def budget():
        return MAX_TUNE - sum(len(p) for p in parts)

    while i < n and budget() > 3:
        c = phonemes[i]

        if c.isspace():
            if last_was_note:
                parts.append('P8')
                last_was_note = False
            i += 1
            continue
        if c in '.!?':
            parts.append('P4')
            last_was_note = False
            i += 1
            continue
        if c == "'":
            pending_stress = True
            i += 1
            continue
        if c == ',':
            parts.append('P16')
            last_was_note = False
            i += 1
            continue
        if c in ':_-=%':
            i += 1
            continue

        digraph = phonemes[i:i + 2]
        notes = None
        consumed = 1
        if digraph in _DIGRAPH_NOTE:
            notes = _DIGRAPH_NOTE[digraph]
            consumed = 2
        elif digraph in _AFFRICATE:
            v = _AFFRICATE[digraph]
            consumed = 2
            if v is None:
                if last_was_note:
                    parts.append('P16')
                    last_was_note = False
                i += consumed
                continue
            notes = v
        elif c in _VOWEL_NOTE:
            notes = [_VOWEL_NOTE[c]]
        elif c in _CONSONANT_BLIP:
            v = _CONSONANT_BLIP[c]
            if v is None:
                if last_was_note:
                    parts.append('P16')
                    last_was_note = False
                i += 1
                continue
            notes = [v]
        else:
            i += 1
            continue

        wanted_len = 8 if pending_stress else 16
        pending_stress = False
        if wanted_len != cur_len:
            if budget() - 2 < 0:
                break
            parts.append('L' + str(wanted_len))
            cur_len = wanted_len

        for note in notes:
            if budget() - len(note) < 0:
                break
            parts.append(note)
            last_was_note = True

        i += consumed

    tune = ''.join(parts)
    if len(tune) > MAX_TUNE:
        tune = tune[:MAX_TUNE]
    return tune, phonemes


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: tts_buzzer.py <text> [lang]', file=sys.stderr)
        sys.exit(1)
    arg_text = sys.argv[1]
    arg_lang = sys.argv[2] if len(sys.argv) > 2 else 'en'
    out_tune, out_phon = tts_to_tune(arg_text, arg_lang)
    print('tune     :', out_tune)
    print('phonemes :', out_phon)
    print('tune_len :', len(out_tune))
