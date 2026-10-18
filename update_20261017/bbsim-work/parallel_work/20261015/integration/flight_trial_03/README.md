# flight_trial_03

Копия flight_trial_02 (тот же исполнитель, порог скорости 0,20, детектор сна, сообщения проверок) с одним отличием: Gazebo загружает кандидат поля `field_measurements_01/generated` (обычные листы 30 × 42 см, чёрные квадраты 29 × 29 см, центры/углы/ID исходной карты). Исходный мир `sim/worlds/aruco_map` не изменён. Карта детектора `map.input.txt` побайтно совпадает с картой поля; это проверяется в run.sh до запуска. SHA всех файлов поля сохраняются в каждом запуске (`field_files.sha256`).

Запуск с Mac: `bash parallel_work/20261015/integration/flight_trial_03/host_run.sh TAG SCENARIO [paused|on]`.
