# Публикация на GitHub

Этот каталог — корень подготовленного репозитория. Старые архивы PowerShell,
локальные тестовые файлы и готовые бинарники в исходный репозиторий не нужны.
Бинарники размещаются в Releases; `release-assets/`, `build/` и `dist/` исключены
через `.gitignore`.

## Самый простой способ — через сайт, без команд

1. Скачайте и распакуйте **AntigravityPatcher-v0.2.0-GitHub-source.zip**.
2. На GitHub нажмите **+ → New repository**, задайте имя, например
   `antigravity-local-patcher`, выберите **Public** и нажмите **Create repository**.
3. Нажмите ссылку **uploading an existing file** в пустом репозитории.
   Если он уже содержит файлы: **Add file → Upload files**.
4. Откройте распакованную папку **AntigravityPatcher**. Перетащите в браузер
   **её содержимое**, включая папку `.github` и файл `.gitignore`.
   Саму внешнюю папку не перетаскивайте: `README.md`, `src/`, `scripts/` и
   `.github/` должны оказаться в корне репозитория.
5. Введите сообщение `Initial version 0.2.0` и нажмите **Commit changes**.
6. Для релизов откройте **Actions → Build releases → Run workflow**.
   Оставьте галочку **Create a draft GitHub Release** включённой и подтвердите
   **Run workflow**. Workflow сам собирает пять архивов и создаёт тег версии.
7. Дождитесь зелёного завершения сборки. Затем **Releases → черновик v0.2.0 →
   Publish release**. После публикации другу можно дать страницу **Releases**.

Папка `.github` обязательна для автоматической сборки. Если Windows скрывает
её, включите **Вид → Показать → Скрытые элементы** в Проводнике. На GitHub
проверьте, что существует `.github/workflows/release.yml`.

Если просто нужно сразу поделиться Windows-версией, можно вручную создать
Release с отдельным тегом, например `v0.2.0-windows`, и прикрепить готовый
Windows ZIP и его `.sha256`. Пять сборок через Actions будут отдельным релизом
`v0.2.0`. Раздельные теги позволяют не мешать автоматическому черновику.

Официальные инструкции: [загрузка файлов через сайт](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
и [публикация Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

## Альтернативный способ — через Git

1. Создайте пустой GitHub-репозиторий, например `antigravity-local-patcher`.
   Не добавляйте автоматически README, license или `.gitignore`: они уже есть.
2. Откройте терминал в этой папке и выполните команды ниже. Замените URL
   `YOUR_USERNAME` своим адресом репозитория.

```bash
git init -b main
git add .
git commit -m "Prepare Antigravity Local Patcher v0.2.0"
git remote add origin https://github.com/YOUR_USERNAME/antigravity-local-patcher.git
git push -u origin main
```

3. Вкладка **Actions** должна показать workflow **Tests**. Дождитесь успеха.
4. Создайте тег первой версии:

```bash
git tag v0.2.0
git push origin v0.2.0
```

5. Дождитесь workflow **Build releases**: он собирает и проверяет Windows x64,
   Linux x64/ARM64 и macOS Intel/Apple Silicon.
6. Откройте **Releases**, найдите созданный **Draft**. Проверьте пять архивов,
   контрольные суммы и описание. Нажмите **Publish release**.
7. Дайте другу ссылку на `https://github.com/YOUR_USERNAME/antigravity-local-patcher/releases/latest`.

Для сборки без создания Release используйте **Actions → Build releases → Run
workflow** и снимите галочку создания черновика. Архивы появятся в разделе
Artifacts завершённого запуска. Для их
скачивания через Actions нужен вход в GitHub; опубликованные Releases удобнее
для обычного скачивания.

Workflow не обновляет уже опубликованный релиз: если тег опубликован, сначала
повысьте версию и создайте новый тег. Для уже опубликованного релиза шаг создания
черновика завершается успешно с уведомлением, оставляя все его файлы без изменений.
При повторном запуске того же тега файлы
можно обновить только в существующем черновике.

## Новая версия

1. Обновите `__version__` в `src/antigravity_patcher/__init__.py` и версию
   `project.version` в `pyproject.toml`.
2. Обновите CHANGELOG, README и `docs/RELEASE_NOTES.md`.
   Также обновите номера версий в `scripts/windows-version.txt`.
3. Запустите тесты, сделайте commit и push.
4. Создайте тег `vНОВАЯ_ВЕРСИЯ`. Workflow проверяет его совпадение с версией кода.

## Ручная сборка

```bash
python -m pip install -r requirements-build.txt
python scripts/build_release.py
```

Готовый архив и `.sha256` будут в `release-assets/`. Собирать каждую платформу
нужно на соответствующей ОС: PyInstaller не создаёт Linux/macOS-бинарники из
Windows. Для кода подписи macOS нужны системные `codesign` и данные реального
`.app`; транзакционные тесты не заменяют проверку на установленном приложении.

## Состояние подготовленного пакета

Windows x64 собирается и проверяется локально. Linux/macOS workflows подготовлены,
но требуют запуска в вашем репозитории; готовность каждого архива подтверждается
только успешным job **Build and smoke-test native executable**. Не называйте их
собранными до этого запуска.
