"""Detached UI worker: prepare/export, then publish after all job handles close."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import sys
import traceback

from full_video_pipeline import execute_job
from rinayaki.job import job_lock
from rinayaki.languages import stored_languages, stored_speaker_count
from rinayaki.project_storage import (checked_cache_job, lifecycle_lock,
    destination_path, publish_locked_project, set_control, is_direct_project)

ROOT = Path(__file__).resolve().parents[1]


def run_job(job: Path, cache_root: Path, phase: str, *, execute=execute_job) -> int:
    direct = is_direct_project(job)
    job = job.resolve() if direct else checked_cache_job(job,cache_root)
    # Do not overwrite the active worker's state when a second launch is rejected.
    with lifecycle_lock(job,cache_root):
        current_phase = phase
        try:
            if direct and phase == 'publish':
                raise ValueError('直接保存的项目不需要迁移。')
            receipt = cache_root/'.transfers'/(job.name+'.json')
            if phase == 'publish':
                if not receipt.exists():
                    manifest = json.loads((job/'intermediates/pipeline.json').read_text(encoding='utf-8'))
                    outputs = manifest.get('outputs',{})
                    videos = [(job/value).resolve() for value in outputs.values() if value.endswith('.mp4')]
                    if manifest.get('status') != 'complete' or not videos or any(not p.is_relative_to(job) or not p.is_file() for p in videos):
                        raise ValueError('成片尚未完成，不能迁移。')
                publish_locked_project(job,cache_root)
                return 0
            if receipt.exists():
                raise ValueError('该任务已进入迁移阶段，请继续迁移，不要重新处理。')
            details = job/'intermediates'
            config = json.loads((details/'destination.local.json').read_text(encoding='utf-8'))
            if not direct and config.get('job_id') != job.name:
                raise ValueError('任务标识不一致。')
            if not direct:
                target = Path(config['destination'])
                destination_path(str(target.parent),target.name,cache_root)
            source = config['source']
            source_language, target_language = stored_languages(source)
            speaker_count = stored_speaker_count(source)
            if (details/'prepared.json').exists():
                prepared = json.loads((details/'prepared.json').read_text(encoding='utf-8'))
                if stored_languages(prepared) != (source_language, target_language):
                    raise ValueError('语言设置与已准备结果不一致，请使用新项目重新处理。')
                if stored_speaker_count(prepared) != speaker_count:
                    raise ValueError('说话人数与已准备结果不一致，请使用新项目重新处理。')
                if phase == 'prepare':
                    set_control(job,cache_root,status='awaiting_style',phase=phase,error=None)
                    return 0
            if source['kind'] not in {'web','local'}:
                raise ValueError('Invalid source kind')
            args = argparse.Namespace(project_dir=job,phase=phase,stem=config['project_name'],
                url=source['source'] if source['kind']=='web' else None,
                input=Path(source['source']) if source['kind']=='local' else None,
                acquisition=source.get('acquisition'),
                yt_dlp=ROOT/'.tools/yt-dlp.exe',ffmpeg=ROOT/'.tools/ffmpeg/ffmpeg.exe',
                translation_batch_size=12,refinement_batch_size=20,
                source_language=source_language,target_language=target_language,speaker_count=speaker_count)
            set_control(job,cache_root,status='running',phase=phase,pid=os.getpid(),error=None)
            with job_lock(job), (details/'launcher.log').open('a',encoding='utf-8') as log:
                with redirect_stdout(log), redirect_stderr(log):
                    try:
                        code = execute(args)
                        if code:
                            raise RuntimeError(f'Pipeline exited with code {code}')
                    except Exception:
                        traceback.print_exc()
                        raise
            if phase == 'prepare':
                set_control(job,cache_root,status='awaiting_style',phase=phase,error=None)
                return 0
            if direct:
                set_control(job,cache_root,status='complete',phase=phase,error=None)
                return 0
            current_phase = 'publish'
            set_control(job,cache_root,status='publishing',phase='publish',stage='queued',error=None)
            # No log/progress writes inside the tree after this point.
            publish_locked_project(job,cache_root)
            return 0
        except Exception as error:
            set_control(job,cache_root,status='failed',phase=current_phase,error=str(error))
            return 1


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--job-id')
    source.add_argument('--project-dir',type=Path)
    parser.add_argument('--phase',choices=('prepare','export','publish'),required=True)
    parser.add_argument('--cache-root',type=Path,default=ROOT.parent/'RinaYakiCache')
    args = parser.parse_args()
    try:
        if args.project_dir and not is_direct_project(args.project_dir):
            raise ValueError('不是可继续处理的直接保存项目。')
        return run_job(args.project_dir or args.cache_root/args.job_id,args.cache_root,args.phase)
    except (OSError,ValueError,RuntimeError) as error:
        print(str(error),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
