"""Local destination metadata and verified project publishing.

The caller must stop all writers and close their file handles before publishing.
This module is deliberately independent of the UI and provider APIs.
"""
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import uuid

from .job import file_digest, fingerprint, job_lock
from .workspace import safe_project_name


def destination_path(parent: str, name: str, cache_root: Path) -> Path:
    if not parent.strip() or not name.strip():
        raise ValueError('请填写保存位置和项目名称。')
    directory = Path(parent.strip()).expanduser()
    if not directory.is_absolute():
        raise ValueError('请选择完整的保存位置。')
    # Lazily create only our own default output, not arbitrary misspelled paths.
    from .settings import default_output_dir
    if directory.absolute() == default_output_dir().absolute():
        for ancestor in (directory, *directory.parents):
            if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()):
                raise ValueError('默认输出目录不能是链接。')
        directory.mkdir(parents=True, exist_ok=True)
    if safe_project_name(name) != name or name in {'.','..'}:
        raise ValueError('项目名称包含无效字符或末尾空格。')
    if len(name) > 100:
        raise ValueError('项目名称请控制在 100 个字符以内。')
    directory = directory.resolve()
    cache = cache_root.resolve()
    result = directory/name
    if result.is_relative_to(cache) or cache.is_relative_to(result):
        raise ValueError('正式项目不能与缓存目录重叠。')
    if not directory.is_dir():
        raise ValueError('保存位置不存在，请先选择一个文件夹。')
    if result.exists():
        raise FileExistsError('该项目名称已存在，请更换名称。')
    # Check actual access without leaving a probe file behind.
    with tempfile.TemporaryFile(dir=directory):
        pass
    return result


def write_local_json(path: Path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        pending.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(pending,path)
    finally:
        pending.unlink(missing_ok=True)


def is_direct_project(job: Path) -> bool:
    try:
        return json.loads((job/'intermediates/destination.local.json').read_text(encoding='utf-8')).get('storage') == 'direct'
    except (OSError,ValueError):
        return False


def create_direct_project(parent: str, name: str, source: dict, cache_root: Path, index: Path) -> Path:
    job = destination_path(parent,name,cache_root)
    job.mkdir()  # Never adopt or overwrite an existing directory implicitly.
    write_local_json(job/'intermediates/destination.local.json',{
        'schema_version':1,'storage':'direct','project_name':name,'source':source,
        'job_id':'job-'+uuid.uuid4().hex[:24]})
    set_control(job,cache_root,status='new',source=source,project_name=name)
    index.parent.mkdir(parents=True,exist_ok=True)
    (index.parent/'.gitignore').write_text('*\n',encoding='utf-8')
    with job_lock(index.parent):
        try:
            projects=json.loads(index.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            projects=[]
        write_local_json(index,list(dict.fromkeys([*projects,str(job)])))
    return job


def create_cached_project(cache_root: Path, parent: str, name: str, source: dict) -> Path:
    destination = destination_path(parent,name,cache_root)
    cache_root.mkdir(parents=True,exist_ok=True)
    # Runtime paths must not be accidentally added if this group becomes a repo.
    (cache_root/'.gitignore').write_text('*\n',encoding='utf-8')
    identity = fingerprint({'source':source,'destination':str(destination)})[:24]
    job = cache_root/('job-'+identity)
    with lifecycle_lock(job,cache_root):
        job.mkdir(exist_ok=True)
        config = job/'intermediates/destination.local.json'
        data = {'schema_version':1,'destination':str(destination),'project_name':name,'source':source,'job_id':job.name}
        if config.exists():
            if json.loads(config.read_text(encoding='utf-8')) != data:
                raise ValueError('缓存任务信息不一致。')
        else:
            write_local_json(config,data)
            set_control(job,cache_root,status='new',source=source,destination=str(destination),project_name=name)
    return job


def checked_cache_job(job: Path, cache_root: Path) -> Path:
    if job.is_symlink() or (hasattr(job,'is_junction') and job.is_junction()):
        raise ValueError('缓存路径不能是链接。')
    job = job.resolve()
    if job.parent != cache_root.resolve() or not re.fullmatch(r'job-[0-9a-f]{24}',job.name):
        raise ValueError('只能操作缓存根目录中的任务文件夹。')
    return job


@contextmanager
def lifecycle_lock(job: Path, cache_root: Path):
    if is_direct_project(job):
        with job_lock(job/'intermediates/.lifecycle'):
            yield
        return
    job = checked_cache_job(job,cache_root)
    # The lock lives outside the tree being moved/deleted.
    with job_lock(cache_root/'.locks'/job.name):
        yield


def control_path(job: Path, cache_root: Path) -> Path:
    if is_direct_project(job):
        return job/'intermediates/control.local.json'
    checked_cache_job(job,cache_root)
    return cache_root/'.control'/(job.name+'.json')


def set_control(job: Path, cache_root: Path, **values):
    path = control_path(job,cache_root)
    try:
        current = json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        current = {}
    current.update(values,updated_at=time.time())
    write_local_json(path,current)


def update_destination(job: Path, cache_root: Path, parent: str, name: str):
    with lifecycle_lock(job,cache_root):
        if (cache_root/'.transfers'/(job.name+'.json')).exists():
            raise ValueError('迁移已开始，请先继续完成迁移；缓存仍保留。')
        destination = destination_path(parent,name,cache_root)
        path = job/'intermediates/destination.local.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data.update(destination=str(destination),project_name=name)
        write_local_json(path,data)
        set_control(job,cache_root,destination=str(destination),project_name=name)
    return destination


def tree_manifest(root: Path) -> dict:
    """Reject redirected entries before copying/deleting any project tree."""
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('项目内含链接或目录联接，不能自动迁移。')
        relative = path.relative_to(root).as_posix()
        result[relative] = {'size':path.stat().st_size,'sha256':file_digest(path)} if path.is_file() else {'directory':True}
    return result


def publish_cached_project(job: Path, cache_root: Path) -> Path:
    with lifecycle_lock(job,cache_root):
        return publish_locked_project(job,cache_root)


def publish_locked_project(job: Path, cache_root: Path) -> Path:
    """Copy, verify, publish without overwriting, then remove ONLY this cache job.

    Always use a verified copy, including same-disk moves, for the first version.
    Interrupted copies reuse the owned pending directory. A transfer receipt
    lets a later call finish cache cleanup after publication was interrupted.
    Must be called under the launcher's external lifecycle lock, with worker
    handles closed. Do not call while ASR/translation/export is still writing.
    """
    root = cache_root.resolve()
    job = checked_cache_job(job,root)
    receipt_path = root/'.transfers'/(job.name+'.json')
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        destination = Path(receipt['destination'])
        before = receipt['manifest']
        if not re.fullmatch(r'\.rinayaki-transfer-[0-9a-f]{32}',receipt['pending']):
            raise ValueError('迁移记录中的临时路径无效。')
    else:
        config = json.loads((job/'intermediates/destination.local.json').read_text(encoding='utf-8'))
        if config.get('job_id') != job.name:
            raise ValueError('缓存任务标识不一致。')
        destination = Path(config['destination'])
        before = tree_manifest(job)
        if destination.exists():
            raise FileExistsError('目标项目已存在，未覆盖，缓存已保留。')
        receipt = {'destination':str(destination),'manifest':before,
                   'pending':'.rinayaki-transfer-'+uuid.uuid4().hex,'phase':'copying'}
        write_local_json(receipt_path,receipt)
    if not destination.is_absolute() or destination.is_symlink() or (hasattr(destination,'is_junction') and destination.is_junction()):
        raise ValueError('迁移目标路径无效。')
    destination = destination.resolve()
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError('目标与缓存目录重叠。')
    set_control(job,root,status='publishing',stage='verifying',destination=str(destination),error=None)
    if receipt.get('phase') != 'published' and (not job.is_dir() or tree_manifest(job) != before):
        raise ValueError('迁移期间缓存内容发生变化，未清理。')
    if receipt.get('phase') == 'published' and not destination.is_dir():
        raise ValueError('已发布的目标被移动或删除，请先恢复目标目录。')
    if destination.exists():
        if tree_manifest(destination) != before:
            raise ValueError('目标目录与缓存不一致，缓存已保留。')
    else:
        pending = destination.parent/receipt['pending']
        if pending.is_symlink() or (hasattr(pending,'is_junction') and pending.is_junction()):
            raise ValueError('迁移临时目录不能是链接。')
        if pending.exists():
            tree_manifest(pending)
        set_control(job,root,status='publishing',stage='copying')
        shutil.copytree(job,pending,dirs_exist_ok=True)
        set_control(job,root,status='publishing',stage='verifying')
        if tree_manifest(pending) != before or tree_manifest(job) != before:
            raise ValueError('迁移校验未通过，缓存已保留。')
        if destination.exists():
            raise FileExistsError('迁移期间出现同名项目，缓存已保留。')
        pending.rename(destination)
    if receipt.get('phase') != 'published':
        receipt['phase'] = 'published'
        write_local_json(receipt_path,receipt)
    if job.exists():
        checked_cache_job(job,root)
        remaining = tree_manifest(job)
        if any(before.get(path) != entry for path,entry in remaining.items()):
            raise ValueError('缓存内容发生变化，未清理。')
        set_control(job,root,status='publishing',stage='cleanup')
        shutil.rmtree(job)
    set_control(job,root,status='complete',stage='published',final_dir=str(destination),error=None)
    receipt_path.unlink(missing_ok=True)
    return destination
