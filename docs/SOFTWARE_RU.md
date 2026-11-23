# Шмель.О — Описание программного обеспечения

*Учебный квадрокоптер «BUMBLEBEE.O». Версия описания: 23.11.2026. English version: [SOFTWARE.md](SOFTWARE.md).*

Здесь описано ПО, которое **сейчас** работает на дронах «Шмель», и как студенты с ним работают.
Скачать образ SD-карты, обновления, наземную станцию и симулятор — на [главной странице репозитория](../README.md).

> **Две линии кода.** Публичный выпуск для скачивания — **образ 1.0.1 + обновление 1.0.2** (ветка `main`).
> Дроны полигона Future Lab работают на более новом и безопасном полётном коде **r2j** (ветка `feat/drone-image-r2j`, в `main` ещё нет)
> и двух пробных изменениях (фильтр позы В1.1 и прореживание кадров передней камеры; ветки `exp/posefix-v11`, `exp/camera-r2m-cam`).
> Где линии ведут себя по-разному, стоят пометки **[r2j]** и **[1.0.2]**.

## 1. Общая архитектура

| Уровень | Где работает | Назначение |
|---|---|---|
| 1 — Бортовое ПО | Raspberry Pi 5 на дроне + PX4 на Pixhawk 6C | Управление полётом, датчики, позиция по меткам ArUco, ROS 2 |
| 2 — Наземная станция и инструменты студента | Ноутбук / ПК студента | Приложение Bumblebee GCS; программы полёта на Python (`drone.py`); rviz2 / rqt |
| 3 — Симулятор | ПК студента (Windows, WSL2) | Gazebo Harmonic + PX4 SITL: проверить программу до настоящего дрона |

Ноутбук и дрон связаны по Wi-Fi (ROS 2 / DDS, MAVLink, HTTP). Gazebo и PX4 — сторонние открытые проекты;
мы даём интеграцию и готовый образ.

## 2. Бортовое ПО (Raspberry Pi 5)

Всё запускается само при включении (служба systemd `bumblebee` → `ros2 launch bumblebee bumblebee.launch.py`).

### 2.1 Операционная система и middleware

| Компонент | Версия на дроне | Роль |
|---|---|---|
| Ubuntu Server | 24.04.4 LTS, ядро 6.8.0-1065-raspi | Операционная система |
| ROS 2 | Jazzy Jalisco (LTS) | Связь узлов на борту |
| MAVROS | 2.14 с тремя исправлениями из основной ветки (#2138, #2149, #2093), своя сборка | Мост ROS 2 ↔ PX4 (MAVLink 2) |
| libcamera | собрана из исходников (ветка Raspberry Pi) | Драйвер камер |
| Python | 3.12 | Программы студентов и часть узлов |

### 2.2 Сеть

- **Режим клиента:** дрон подключается к вашему Wi-Fi (DHCP). Имя дрона — `Bumblebee-XXXX` (по MAC Wi-Fi); GCS находит его по имени.
- **Точка доступа:** если знакомого Wi-Fi нет, дрон поднимает свою сеть `Bumblebee-XXXX` (пароль `12345678`), адрес дрона `10.42.0.1`.
  Кнопка **Add drone** в GCS переводит дрон в ваш Wi-Fi.
- **Несколько дронов в одном Wi-Fi:** у каждого дрона свой домен ROS. Перед `ros2`, rviz2 или rqt на ноутбуке выполните
  `export ROS_DOMAIN_ID=<n>` с номером этого дрона (см. [drone/README.md](../drone/README.md)).
- **SSH:** пользователь `lb`. Пароль по умолчанию — в [drone/README.md](../drone/README.md); **смените его после первого включения.**

### 2.3 Полётный контроллер

| Параметр | Значение |
|---|---|
| Плата | Holybro Pixhawk 6C, отдельно от Raspberry Pi |
| Прошивка | PX4 Autopilot 1.16.1 (`px4_fmu-v6c_default`) |
| Планер | Generic Quadrotor X (`SYS_AUTOSTART` 4001); моторы по PWM 400 Гц |
| Связь с Pi | MAVLink 2, UART `/dev/ttyAMA0`, **921 600 бод** (скорость дрон находит сам при запуске) |
| Поток и дальномер | Holybro H-Flow по CAN (DroneCAN) |
| QGroundControl | по Wi-Fi, TCP-порт 5760 |

Режимы: **Stabilized, Altitude, Position** (переключатель пульта, канал 6), **Offboard** (программы студентов), **Land**.
В настройках PX4 учебных дронов горизонтальная скорость ограничена 0,25 м/с.

### 2.4 Узлы ROS 2 на дроне

| Узел | Что делает |
|---|---|
| `/mavros` | Связь с PX4: телеметрия, команды, параметры |
| `/simple_offboard` | Сервисы полёта: `navigate`, `land`, `get_telemetry`, `set_position`, `set_velocity`, `set_attitude`, `set_rates`, `set_yaw`, `set_yaw_rate`, `set_altitude`, `navigate_global`, `release`. **[r2j]** сажает дрон через 2 с, если программа полёта упала |
| `/aruco_detect` | Находит метки ArUco нижней камерой, считает позицию дрона по карте меток |
| `/vpe_publisher` (`vpe_fix.py`) | **Передаёт позицию по меткам в PX4** (~30 раз в секунду). Вторая задача — безопасная запись параметров PX4 (`/vpe_fix/set_param`, `/vpe_fix/revert_all`). **[r2j]** позы идут только в OFFBOARD и LAND |
| `setpoint_freshness` **[r2j]** | Не пропускает к MAVROS устаревшие (> 0,5 с) команды полёта |
| `main_camera`, `second_camera` (+ `*_camera_fix`) | Нижняя и передняя камеры. **[проба r2m_cam]** передняя — 5 кадров/с |
| `wheel_rc`, `servo_rc` | Колёсный модуль (канал пульта 7) и серво захвата (канал 9) |
| `rosbridge_websocket`, `ros_mjpeg_server` (порт 8080), `tf2_web_republisher` | Веб-доступ: GCS, веб-панель, видео камер |
| статические TF, `qos_relay`, `bumblebee_unified_controller` | Системы координат, согласование QoS, плата LED/серво |

Отдельные службы (не из launch): `notify-manager` (свет и звук уведомлений), `wifi-manager`, сторожа.

### 2.5 Позиционирование (без GPS)

- Позиция — по **меткам ArUco на полу**, их видит нижняя камера «рыбий глаз»; PX4 объединяет её с потоком и дальномером H-Flow.
- Карта меток полигона (`aruco_pose/map/map.txt`): **20 меток, ID 0–16, 18, 19, 20** (17 нет); метка 0 — 0,19 м, остальные 0,29 м.
- Фиксация курса: 2 метки в течение 1,5 с **или** одна метка 3 с при разбросе курса меньше 8°.
- **[проба В1.1]** сомнительная поза по одной метке не выбрасывается, а уходит в PX4 с большой погрешностью.

### 2.6 Свет, звук, колесо и захват

- LED: 6 полос (`LED_1` … `LED_6`), пиксели 0–10, плата на I2C `/dev/i2c-1`, адрес `0x30`.
  Анимации `led_solid`, `led_blink`, `led_breathe`, `led_rainbow`, `led_rotate`, `led_wipe`, `led_pulse`, `led_strobe`; пиксели — `set_led(strip, led, r, g, b)`.
- Звук: мелодии играет **пищалка полётного контроллера PX4** (`/mavros/play_tune`): `play_sound('takeoff')`, `play_tune(drone.TUNE_MARIO)`, `list_sounds()`.
- Плата I2C `0x30`: угол серво 0–255, скорость мотора колеса 0–255 (128 — стоп), две температуры (`read_temperature()`).

## 3. Работа с ноутбука

| Инструмент | Для чего |
|---|---|
| **Bumblebee GCS 1.3.0** (Windows 10/11 x64, macOS 14+) | Находит дроны по имени, добавляет новый дрон в ваш Wi-Fi, показывает телеметрию, свет и звук. **Только наблюдает:** не взводит, не меняет режим, не пишет параметры PX4. Раздел **Flight**: редактор карты меток с картой видимости, проверка программы на Python, 2D-симуляция. *Сервер заданий, с которым он говорит, пока не стоит ни на одном дроне.* |
| SSH / VS Code Remote-SSH | Править и запускать программы на дроне |
| rviz2, rqt, rqt_image_view | Позиция, метки, TF, топики (сначала `ROS_DOMAIN_ID`) |
| QGroundControl | Параметры и калибровки PX4 (преподаватель) |

Программы студентов лежат на дроне в `~/ros2_ws/src/bumblebee/examples/`.

## 4. Библиотека `drone.py`

```python
import sys
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone
```

### 4.1 Запуск и безопасность
| Функция | Описание |
|---|---|
| `enable_safe_interrupt()` | Ctrl+C ставит `should_land=True`, программа сама сажает дрон |
| `check_flight_profile(profile_name)` **[r2j]** | Читает профиль PX4 `INDOOR_ARUCO_SLOW`; примеры не взлетают (код выхода 3), если он не совпал |
| `get_fcu_status()`, `read_px4_params()` | Состояние полётного контроллера, чтение параметров PX4 |

### 4.2 Телеметрия
| Функция | Возвращает |
|---|---|
| `get_telemetry(frame_id=...)` | x, y, z, vx, vy, vz, roll, pitch, yaw, напряжение, режим, armed, connected |
| `get_pos(frame_id='map')` | `(x, y, z)` |
| `print_pos(phase='INFO')`, `print_pos_fresh()` | Печатает `[phase] x=… y=… z=… armed=… mode=…` |
| `vision_pose_age()` | Сколько секунд назад пришла поза по меткам |

### 4.3 Полёт (с ожиданием)
| Функция | По умолчанию | Описание |
|---|---|---|
| `takeoff(height=1.0, speed=0.4, vision_timeout=25.0)` | | Взвод (после проверок) и подъём; на подъём 30 с |
| `fly_to(x, y, z=1.0, speed=0.5)` | `tolerance=0.2` | Полёт в точку системы `map` |
| `move(x=0, y=0, z=0, speed=0.5)` | | Смещение от дрона (`body`: вперёд / влево / вверх) |
| `navigate_wait(...)` | `frame_id='body'`, `vision_timeout=6.0` | Полный контроль: система, курс, допуск, тайм-аут |
| `hover(seconds=3.0)` | | Висеть на месте |
| `safe_land(x=None, y=None)` | `precision_tolerance=0.07`, `timeout=25` | Рекомендуемая посадка; над точкой, если задана; проверяет касание |
| `land()` | | Даёт команду LAND и сразу возвращается |

### 4.4 Полёт без ожидания и режимы
| Функция | Описание |
|---|---|
| `navigate(**kwargs)` | Отправляет цель и сразу возвращается |
| `set_mode(mode)` | Сменить режим PX4. **[r2j]** отказ, пока летит пилот (взведён не в OFFBOARD) |
| `arming(value)` | **[r2j]** `arming(True)` всегда отказ — моторы запускаются только через `takeoff()` / `navigate(auto_arm=True)` после проверок; `arming(False)` — только на земле. **[1.0.2]** взводит и разоружает |
| `set_param(param_id, value, ttl_sec=0.0, persistent=False)` | Параметр PX4 через `vpe_fix`, откат при разоружении |
| `apply_flight_profile(name)` | **[r2j]** только сверяет (ничего не пишет; значения ставят один раз в QGC). **[1.0.2]** пишет `INDOOR_ARUCO` / `INDOOR_ARUCO_SLOW` |

`set_position`, `set_velocity`, `set_attitude`, `set_rates`, `set_yaw`, `set_yaw_rate` — это **сервисы ROS** узла `simple_offboard`, а не функции `drone.py`.

### 4.5 Метки
| Функция | Описание |
|---|---|
| `check_aruco(timeout=10, min_markers=1)` | **[r2j]** возвращает список увиденных ID (пустой — меток нет) |
| `require_aruco(min_markers=1, timeout=15.0)` | `RuntimeError`, если меток мало |
| `set_aruco_map(markers, map_file)` | **[r2j]** сверяет карту программы с картой дрона (ошибка при расхождении). **[1.0.2]** записывает карту |
| `wait_yaw_lock(timeout)`, `yaw_lock_age()` | Ждать фиксации курса; секунд с последней фиксации |
| `require_vpe_link(min_hz=8.0, timeout=15.0)` | Ждать ровного потока позы в PX4 |
| `wait_position_stable(stable_secs=3, ...)` | Ждать, пока позиция PX4 успокоится (0,15 м) |

### 4.6 Свет, звук, серво
`set_led`, `led_solid`, `led_blink`, `led_breathe`, `led_rainbow`, `led_rotate`, `led_wipe`, `led_pulse`, `led_strobe`, `led_off`,
`led_take_control`, `led_release_control`, `play_sound(name)`, `play_tune(tune)`, `list_sounds()`, `beep()`,
`set_servo_angle`, `set_servo_speed`, `read_temperature`.

### 4.7 Встроенные сторожа (во время каждого манёвра)
- Нет новой позы по меткам 6 с (25 с на взлёте) → **посадка (LAND)**.
- Нет телеметрии дольше 5 с → отказ манёвра, **посадка**.
- Скачок позиции быстрее ~3 м/с → **посадка**.
- Высота ниже точки взвода на 0,5 м → **[r2j] посадка** ([1.0.2] — разоружение).
- **[r2j]** Подъём на 0,6 м выше цели → **посадка**; программа упала → `simple_offboard` сажает через 2 с.

## 5. Системы координат

| `frame_id` | Ноль | Применение |
|---|---|---|
| `map` | Ноль карты меток (метка 0 в `map.txt`) | Абсолютные точки: `fly_to(1.5, 0, 1.0)` |
| `body` | Центр дрона, X вперёд, Y влево, Z вверх | Относительные манёвры: `move(1.0, 0, 0)` — 1 м вперёд |
| `aruco_<id>` | Центр метки `<id>` (пока она в кадре) | Полёт и посадка над меткой |

Правило ROS: +X вперёд, **+Y влево**, +Z вверх.

## 6. Основные топики и сервисы ROS 2

| Имя | Тип | Примечание |
|---|---|---|
| `/mavros/mavros/pose` | `geometry_msgs/PoseStamped` | Позиция и ориентация PX4 (переназначено с `local_position/pose`) |
| `/mavros/mavros/velocity_body` | `geometry_msgs/TwistStamped` | Скорость в системе дрона |
| `/mavros/state` | `mavros_msgs/State` | Режим, armed, connected (RELIABLE + TRANSIENT_LOCAL) |
| `/aruco_detect/markers` | `aruco_pose/MarkerArray` | Метки в кадре |
| `/aruco_detect/markers_used` | `std_msgs/Int32` | Сколько меток в расчёте позы, каждый кадр |
| `/aruco_detect/yaw_locked` | `std_msgs/Bool` | Фиксация курса, каждый кадр |
| `/navigate`, `/get_telemetry`, `/land` | сервисы `simple_offboard` | Полёт в точку, телеметрия, посадка |
| `/vpe_fix/set_param`, `/vpe_fix/revert_all` | сервисы | Безопасная запись / откат параметров PX4 |

Политики QoS издателя и подписчика должны совпадать — иначе данные молча не приходят.

## 7. Примеры

Готовые программы: `examples/flight/flight.py`, `flight_marker.py`, `flight_marker_loop.py` (сначала проверяют профиль PX4).

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

drone.enable_safe_interrupt()
if not drone.check_aruco(timeout=10):
    sys.exit("Метки не видны.")
if not drone.wait_position_stable(stable_secs=3):
    sys.exit("Позиция не успокоилась.")
drone.takeoff(0.9)
drone.hover(5.0)
drone.safe_land(x=0, y=0)
```

```python
drone.takeoff(0.9)
drone.fly_to(1.5, 0.0, 0.9)    # по +X карты меток
drone.fly_to(1.5, 1.5, 0.9)    # по +Y карты (влево от +X)
drone.fly_to(0.0, 0.0, 0.9)    # к нулю карты
drone.safe_land()
```

```python
drone.led_solid(0, 255, 0, duration=2.0)   # зелёный — готов
drone.play_sound('takeoff')
drone.takeoff(0.9)
drone.safe_land()
drone.play_sound('land')
```

Взлетайте примерно на 0,9 м и выше: тягу висения PX4 узнаёт только выше ~1 м.

## 8. Симулятор (Gazebo)

- **Gazebo Harmonic + PX4 SITL** (PX4 v1.16.0, модель `gz_x500_mono_cam_down`) с теми же узлами ROS 2 (`aruco_detect`, `vpe_fix`, `simple_offboard`) и тем же `drone.py`
  (свет, пищалка, серво и колесо — заглушки).
- **Windows:** готовый образ WSL2 `BumblebeeSim` (~3,7 ГБ, ссылка на главной странице); программа запускается командой `sim-run flight.py`.
  Linux: `ros2 launch bumblebee_sim bumblebee_sim.launch.py` или `run_sim.sh`.
- MAVROS ↔ PX4 SITL: `udp://:14540@127.0.0.1:14580`.
- **Важно:** симулятор — не дрон. Gazebo обрабатывает камеру примерно в 3 раза быстрее Raspberry Pi
  (детектор на дроне ≈ 8,5 кадра/с) и использует свою карту меток. Программу, которая летает в Gazebo, на дроне всё равно проверять осторожно.

## 9. Версии и лицензии

| Компонент | Где | Версия | Автор | Лицензия |
|---|---|---|---|---|
| Ubuntu Server | дрон | 24.04.4 LTS | Canonical | открытая |
| ROS 2 | дрон, ПК | Jazzy | Open Robotics | Apache 2.0 |
| MAVROS | дрон | 2.14 + исправления | сообщество ROS | GPLv3 / LGPLv3 / BSD |
| PX4 Autopilot | Pixhawk 6C, SITL | 1.16.1 (SITL 1.16.0) | PX4 / Dronecode | BSD 3-Clause |
| libcamera | дрон | ветка Raspberry Pi | Raspberry Pi / libcamera | LGPL |
| Узлы Шмеля, `drone.py`, GCS, настройка симулятора | дрон, ПК | 1.0.2 / r2j; GCS 1.3.0 | FutureLab | **Apache 2.0** |
| `simple_offboard`, `aruco_pose` (на основе Clover) | дрон | — | Copter Express / FutureLab | MIT |
| Gazebo | ПК | Harmonic | Open Robotics | Apache 2.0 |

© 2026 FutureLab — Future Lab Industries L.L.C – S.P.C, Абу-Даби, ОАЭ. См. [LICENSE](../LICENSE) и [NOTICE](../NOTICE).
