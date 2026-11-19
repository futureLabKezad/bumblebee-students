"""bbflight -- Bumblebee GCS "Flight" module, shared Python (17.11.2026).

Pure Python 3.12, no numpy: the same files run on the PC (tests), in the
browser (Pyodide, the GCS module) and later on the drone’s Pi.

    bbmap      marker map format v1: parse, check, canonical map.txt, sha256
    coverage   how many markers the down camera sees at a point of the field
    codecheck  check a student’s Python program before it is sent (layer 1)
    fakedrone  a "not real" drone with the drone.py API, for the simulation
    simrun     run a program on the fake drone and collect path + warnings

Nothing here talks to a drone, arms, or changes PX4 settings.
"""
__version__ = '0.1.0'
