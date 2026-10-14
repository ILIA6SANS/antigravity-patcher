# Antigravity Local Patcher

> [!WARNING]
> **⚠️ Проверено только на Windows.** Работа с Antigravity на Linux и macOS пока не проверена.
>
> Если что-то не работает, создайте обращение в **Issues → New issue** — постараемся разобраться и помочь. Укажите ОС, архитектуру, версию Antigravity и сообщение об ошибке.

**CLI · Antigravity 2.0 / Manager · IDE**

Локальный патчер проверок доступности Antigravity для **Windows, Linux и macOS**.
Интерфейс и команды — на английском, инструкция — на русском.

- Автоматически находит установленные CLI, Manager и IDE.
- Ищет уникальные сигнатуры, проверяя архитектуру и исполняемые секции.
- Сохраняет оригиналы вне папки приложения и проверяет SHA256 после записи.
- Возвращает оригиналы через Restore; блокирует откат поверх обновления.
- Работает офлайн, не читает токены аккаунта и не выполняет сетевых запросов.
- Релизные сборки запускаются без установленного Python.

Это неофициальный проект. Он меняет локальные проверки клиента; доступность
моделей и функций по-прежнему зависит от ответа Google. Статус `patched`
подтверждает изменение файла, а не успешный доступ к сервису.

## Скачать и запустить

Откройте **Releases** на странице репозитория. Выберите архив своей системы:

| Система | Архив для v0.2.0 | Запускаемый файл внутри |
|---|---|---|
| Windows 10/11, x64 | `antigravity-patcher-v0.2.0-windows-x64.zip` | `AntigravityPatcher.exe` |
| Linux, x64 | `antigravity-patcher-v0.2.0-linux-x64.tar.gz` | `AntigravityPatcher` |
| Linux, ARM64 | `antigravity-patcher-v0.2.0-linux-arm64.tar.gz` | `AntigravityPatcher` |
| macOS, Intel | `antigravity-patcher-v0.2.0-macos-x64.tar.gz` | `AntigravityPatcher` |
| macOS, Apple Silicon | `antigravity-patcher-v0.2.0-macos-arm64.tar.gz` | `AntigravityPatcher` |

Нужно распаковать **весь архив**: исполняемый файл использует вложенную папку
`_internal`. Один EXE, скопированный отдельно, не запустится. Это обычная
переносимая сборка без установки Python и без установщика.

1. Закройте Antigravity, его окна и фоновые процессы, включая CLI.
2. Распакуйте архив в отдельную папку.
3. В Windows запустите `AntigravityPatcher.exe` двойным щелчком.
4. Выберите **1 — Patch all detected installations**.
5. После сообщения `[ok]` снова запустите Antigravity и войдите обычным способом.

На Linux и macOS запустите из терминала:

```bash
cd AntigravityPatcher
./AntigravityPatcher
```

Меню:

```text
1  Patch all detected installations
2  Show status
3  Restore originals
4  Set custom file paths
0  Exit
```

Если система запрещает запись в системную папку установки, нужны права на эту
папку. В Windows можно запустить распакованный EXE от имени администратора.
Храните весь распакованный пакет в папке, недоступной для записи другим
пользователям. Для Linux/macOS выберите установку своего пользователя или
выполните нужную команду с соответствующими правами. Если используется другой
пользователь, укажите один и тот же `--backup-dir` для Patch и Restore.

Сборки не имеют подписи издателя; macOS-сборки не нотарифицированы. Если система
блокирует скачанный патчер, проверьте источник и контрольную сумму архива и
используйте штатное разрешение запуска в настройках системы.

## Что он патчит

| Компонент | Файл | Изменение |
|---|---|---|
| CLI | `agy.exe` / `agy` | Локальная ветка eligibility |
| Antigravity 2.0 / Manager | `resources/bin/language_server.exe` / `language_server` | Локальный флаг `hasValidAuth` |
| IDE | `resources/app/out/main.js` | Локальная ветка входа после `resetIsTierGCPTos()` |

В `.app`-пакетах macOS пути начинаются с `Contents/Resources/`.
Бинарные сигнатуры предусмотрены для x64 и ARM64. JavaScript-патч IDE не зависит
от архитектуры. Расширения других редакторов в этой версии не обрабатываются.

**Поддержка всех версий не обещается.** Патчер не привязан к фиксированным
смещениям, но сигнатура должна совпасть с известной. Если её нет, она повторяется
или одновременно найден исходный и изменённый вариант, запись блокируется.
Смешанные Universal Mach-O сборки намеренно не патчатся.

Сигнатуры адаптированы из [QNIX-Dev/eligibility-antigravity-patcher](https://github.com/QNIX-Dev/eligibility-antigravity-patcher)
с сохранением лицензии MIT. Для исходного контекста CLI в upstream указан
CLI 1.2.16; для Manager — 2.19.1. Это происхождение сигнатур, а не обещание работы
любой более ранней или поздней версии.

## Командная строка

В Windows:

```powershell
.\AntigravityPatcher.exe status
.\AntigravityPatcher.exe patch
.\AntigravityPatcher.exe patch cli
.\AntigravityPatcher.exe patch manager ide
.\AntigravityPatcher.exe restore
```

На Linux/macOS те же команды начинаются с `./AntigravityPatcher`.
Без списка компонентов обрабатываются все найденные установки.
Каждая установка — отдельная транзакция: успешный патч одной не откатывается,
если другая оказалась неподдерживаемой.

Для нестандартной установки укажите **путь к файлу**, не к папке:

```powershell
.\AntigravityPatcher.exe patch cli --path-cli "D:\Tools\agy.exe"
.\AntigravityPatcher.exe patch ide --path-ide "D:\Antigravity\resources\app\out\main.js"
```

```bash
./AntigravityPatcher patch manager --path-manager /opt/antigravity/resources/bin/language_server
./AntigravityPatcher patch ide --path-ide "/Applications/Antigravity IDE.app/Contents/Resources/app/out/main.js"
```

Для некоторых Electron-приложений macOS перед локальной переподписью требуется
отдельное разрешение Library Validation. Если патчер сообщил об этом, он ещё
не записал патч. Для нужного приложения можно явно повторить команду:

```bash
./AntigravityPatcher patch ide --macos-disable-library-validation
```

Флаг добавляет исключение в главный исполняемый файл выбранного `.app`, позволяя
ему загружать библиотеки после ad-hoc переподписи. Глобальные настройки macOS
не меняются. Исходные данные подписи сохраняются для отката.

## Статусы и откат

| Статус | Значение |
|---|---|
| `ready` | Найдена одна известная исходная сигнатура |
| `patched` | Найдена одна известная изменённая сигнатура |
| `unsupported` | Неизвестный формат, архитектура или неоднозначная сигнатура |

Папки резервных копий по умолчанию:

- Windows: `%LOCALAPPDATA%\AntigravityPatcher\backups`
- Linux: `$XDG_STATE_HOME/antigravity-patcher/backups` или `~/.local/state/antigravity-patcher/backups`
- macOS: `~/Library/Application Support/AntigravityPatcher/backups`

Оригиналы разных версий сохраняются отдельно. Не удаляйте резервные копии до
восстановления. Для отката выберите **3 — Restore originals** или команду
`restore`. Если обновление уже заменило файл, старый оригинал поверх него не
записывается. После обновления снова выполните `patch`, если новая сигнатура
поддерживается.

На macOS восстановление выбранного `.app` возвращает все файлы, изменённые
в записанной транзакции, вместе с исходной подписью пакета.
После изменения IDE переименовываются только каталоги JavaScript-кэша
`CachedData` и `Code Cache/js` в известных профилях Antigravity; приложение
создаёт новые кэши. Профили `User` и базы сессии не меняются.

Резервные копии старого Windows PowerShell-патчера (`.agpatch-state` и
`.agpatch-backups`) распознаются при `restore`, если их контрольные суммы
совпадают. Сам факт старого патча без пригодной резервной копии для отката
недостаточен.

## Самопроверка и контрольные суммы

```powershell
.\AntigravityPatcher.exe --version
.\AntigravityPatcher.exe --self-test
Get-FileHash .\antigravity-patcher-v0.2.0-windows-x64.zip -Algorithm SHA256
```

```bash
./AntigravityPatcher --self-test
sha256sum -c SHA256SUMS.txt       # Linux
shasum -a 256 -c SHA256SUMS.txt   # macOS
```

`--self-test` использует только временные файлы и не обращается к установленным
приложениям и их кэшам. Полные тесты проверяют нужные изменения байтов, форматы
PE/ELF/Mach-O, неоднозначные сигнатуры, откат, повреждённые резервные копии и
защиту от отката поверх обновления. Синтетические тесты не подтверждают доступ
конкретного Google-аккаунта к моделям.

## Запуск из исходников

Нужен Python 3.10 или новее. У приложения нет сторонних runtime-зависимостей.

```bash
python -m pip install --no-deps .
antigravity-patcher status
antigravity-patcher
```

Для тестов без установки пакета:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## Сборка и публикация

В [инструкции для владельца репозитория](docs/PUBLISHING.md) описаны загрузка
на GitHub, создание тега и публикация первого релиза.

```bash
python -m pip install -r requirements-build.txt
python scripts/build_release.py
```

Сборка создаётся для текущей ОС и архитектуры. GitHub Actions собирает пять
вариантов на собственных Windows, Linux и Mac runners, запускает тесты и
проверяет каждый упакованный исполняемый файл. Push тега `v0.2.0` создаёт
**черновик Release** с архивами и SHA256SUMS; владелец затем публикует его.
Ручной запуск **Actions → Build releases → Run workflow** по умолчанию также
создаёт черновик Release. Если снять галочку **Create a draft GitHub Release**,
он создаст только Actions artifacts. Команды Git для этого не требуются.

## Лицензия

[MIT](LICENSE). Происхождение адаптированного кода описано в
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
