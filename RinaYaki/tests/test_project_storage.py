import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rinayaki.project_storage import create_cached_project, destination_path, publish_cached_project, tree_manifest, lifecycle_lock, update_destination


class ProjectStorageTests(unittest.TestCase):
    def test_only_default_output_is_created_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            home=root/'profile'
            with patch('rinayaki.settings.default_output_dir', return_value=home/'output'):
                output=home/'output'
                self.assertFalse(output.exists())
                self.assertEqual(destination_path(str(output),'demo',root/'cache'),output/'demo')
                self.assertTrue(output.is_dir())
                self.assertFalse((output/'demo').exists())
                with self.assertRaises(ValueError):
                    destination_path(str(root/'typo'),'demo',root/'cache')
                self.assertFalse((root/'typo').exists())

    @unittest.skipUnless(os.environ.get('RINAYAKI_TEST_CROSS_VOLUME_ROOT'),'opt-in cross-volume test')
    def test_cross_volume_publication(self):
        with tempfile.TemporaryDirectory(dir=os.environ['RINAYAKI_TEST_CROSS_VOLUME_ROOT']) as source_directory, tempfile.TemporaryDirectory() as target_directory:
            root=Path(source_directory)
            target=Path(target_directory)
            if root.stat().st_dev==target.stat().st_dev:
                self.skipTest('two distinct filesystem volumes required')
            job=create_cached_project(root/'cache',str(target),'跨盘 项目',{'url':'fixture'})
            (job/'video.mp4').write_bytes(b'x'*1024*1024)
            before=tree_manifest(job)
            final=publish_cached_project(job,root/'cache')
            self.assertEqual(tree_manifest(final),before)
            self.assertFalse(job.exists())
    def test_active_worker_blocks_publication_and_destination_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            cache=root/'cache'
            job=create_cached_project(cache,str(root),'demo',{'url':'fixture'})
            with lifecycle_lock(job,cache):
                with self.assertRaises(RuntimeError):
                    publish_cached_project(job,cache)
                with self.assertRaises(RuntimeError):
                    update_destination(job,cache,str(root),'renamed')
            self.assertTrue(job.exists())

    def test_partial_cleanup_can_resume_after_config_was_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            cache=root/'cache'
            job=create_cached_project(cache,str(root),'demo',{'url':'fixture'})
            (job/'video.mp4').write_bytes(b'fixture')
            def partial_delete(path):
                (path/'intermediates/destination.local.json').unlink()
                raise PermissionError('fixture locked file')
            with patch('rinayaki.project_storage.shutil.rmtree',side_effect=partial_delete):
                with self.assertRaises(PermissionError):
                    publish_cached_project(job,cache)
            self.assertTrue((root/'demo/video.mp4').exists())
            self.assertEqual(publish_cached_project(job,cache),root/'demo')
            self.assertFalse(job.exists())

    def test_corrupted_copy_never_deletes_source(self):
        with tempfile.TemporaryDirectory() as directory:
            import shutil
            root=Path(directory)
            cache=root/'cache'
            job=create_cached_project(cache,str(root),'demo',{'url':'fixture'})
            (job/'video.mp4').write_bytes(b'fixture')
            real_copy=shutil.copytree
            def corrupt(src,dst,*args,**kwargs):
                real_copy(src,dst,*args,**kwargs)
                if Path(src)==job:
                    (Path(dst)/'video.mp4').write_bytes(b'broken')
            with patch('rinayaki.project_storage.shutil.copytree',side_effect=corrupt):
                with self.assertRaises(ValueError):
                    publish_cached_project(job,cache)
            self.assertTrue(job.exists())
            self.assertFalse((root/'demo').exists())
    def test_required_fields_conflicts_and_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root/'cache'
            for parent,name in [('', 'demo'),(str(root),''),('relative','demo'),(str(root),'../demo'),(str(root),'CON')]:
                with self.assertRaises(ValueError):
                    destination_path(parent,name,cache)
            cache.mkdir()
            with self.assertRaises(ValueError):
                destination_path(str(root),'cache',cache)

    def test_verified_publish_preserves_tree_and_deletes_only_own_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root/'cache'
            job = create_cached_project(cache,str(root),'测试 项目',{'url':'fixture'})
            self.assertEqual(create_cached_project(cache,str(root),'测试 项目',{'url':'fixture'}),job)
            (job/'video.mp4').write_bytes(b'fixture video')
            other = cache/'unrelated'
            other.mkdir()
            before = tree_manifest(job)
            final = publish_cached_project(job,cache)
            self.assertEqual(tree_manifest(final),before)
            self.assertFalse(job.exists())
            self.assertTrue(other.is_dir())

    def test_failed_copy_keeps_cache_and_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            cache=root/'cache'
            job=create_cached_project(cache,str(root),'demo',{'url':'fixture'})
            with patch('rinayaki.project_storage.shutil.copytree',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    publish_cached_project(job,cache)
            self.assertTrue(job.exists())
            self.assertFalse((root/'demo').exists())
            self.assertTrue(publish_cached_project(job,cache).is_dir())

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            job=create_cached_project(root/'cache',str(root),'demo',{'url':'fixture'})
            (root/'demo').mkdir()
            with self.assertRaises(FileExistsError):
                publish_cached_project(job,root/'cache')
            self.assertTrue(job.exists())
