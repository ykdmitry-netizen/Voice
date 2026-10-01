"""Патч запуска Python для сред, где каталоги с правами 0o700 недоступны.

Проверено: каталог, созданный как `os.mkdir(path, 0o700)`, становится
недоступным для записи, а именно так работает `tempfile.mkdtemp()`. Из-за этого
ломаются pip, huggingface_hub и вообще любая библиотека, которая готовит файлы
во временном каталоге.

Файл устанавливается в `pylibs` и подхватывается автоматически: `pylibs`
попадает в PYTHONPATH, а CPython при старте импортирует оттуда `sitecustomize`.
На обычной машине патч безвреден — он лишь меняет права создаваемых временных
каталогов с 0o700 на 0o755. Любая ошибка здесь не должна ломать запуск, поэтому
всё завёрнуто в try/except.
"""

import os
import tempfile


def _install() -> None:
    if os.name != "nt":
        return
    if not hasattr(tempfile, "_sanitize_params") or not hasattr(tempfile, "TMP_MAX"):
        return  # незнакомая версия CPython — лучше ничего не менять

    def _mkdtemp(suffix=None, prefix=None, dir=None):
        # _sanitize_params возвращает (prefix, suffix, dir, output_type);
        # число элементов отличается между версиями CPython, берём первые три.
        params = tempfile._sanitize_params(prefix, suffix, dir)
        prefix, suffix, dir = params[0], params[1], params[2]
        for _ in range(tempfile.TMP_MAX):
            name = next(tempfile._get_candidate_names())
            path = os.path.join(dir, prefix + name + suffix)
            try:
                os.mkdir(path, 0o755)
                return path
            except FileExistsError:
                continue
        raise FileExistsError(
            tempfile._errno.EEXIST, "No usable temporary directory name found"
        )

    tempfile.mkdtemp = _mkdtemp
    tempfile.TemporaryDirectory._mkdtemp = staticmethod(_mkdtemp)


try:
    _install()
except Exception:  # noqa: BLE001 - патч не должен мешать запуску
    pass
