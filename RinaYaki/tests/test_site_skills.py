"""Site capability skills stay isolated and never invent unknown locks."""
import unittest

from rinayaki.site_skills import diagnose_error, extractor_args, inspect_capabilities, quality_choices
from rinayaki.site_skills.bilibili import display_label


class SiteSkillTests(unittest.TestCase):
    def test_bilibili_missing_formats_become_compact_locked_choices(self):
        warning = ('WARNING: Format(s) 4K 超清, 1080P 60帧, 720P 高清 are missing; '
                   'you have to become a premium member to download them.')
        result = inspect_capabilities(
            'https://www.bilibili.com/video/BV1xx411c7mD', {}, warning)
        self.assertEqual(result['site'], 'bilibili')
        self.assertEqual(
            [(item['label'], item['requirement'])
             for item in result['locked_qualities']],
            [('4K 超清', 'premium'), ('1080P 60帧', 'premium'),
             ('720P 高清', 'premium')])
        self.assertTrue(all(item['action']['kind'] == 'open_source'
                            for item in result['locked_qualities']))
        self.assertIn('1080P 60帧', result['locked_qualities'][1]['message'])

    def test_known_sites_are_routed_without_cross_site_rules(self):
        self.assertEqual(inspect_capabilities(
            'https://youtube.com/watch?v=abcdefghijk', {}, '')['site'], 'youtube')
        self.assertEqual(inspect_capabilities(
            'https://www.mellow-fan.com/movie/example',
            {'availability': 'subscriber_only'}, '')['site'], 'mellowfan')
        generic = inspect_capabilities('https://video.example/movie/one', {}, '')
        self.assertEqual(generic['site'], 'generic')
        self.assertEqual(generic['locked_qualities'], [])

    def test_site_specific_runtime_and_short_errors(self):
        youtube = 'https://www.youtube.com/watch?v=abcdefghijk'
        self.assertEqual(extractor_args(youtube, {'node'}), ['--js-runtimes', 'node'])
        self.assertEqual(extractor_args(youtube, set()), [])
        self.assertEqual(diagnose_error(youtube, 'Sign in to confirm you are not a bot'),
                         'YouTube 需要登录验证。')
        self.assertEqual(diagnose_error(
            'https://www.mellow-fan.com/movie/example', 'Recv failure: Connection was reset'),
            'Mellow-Fan 连接失败，请稍后重试。')

    def test_bilibili_keeps_full_site_labels_and_groups_codecs(self):
        data = {'_rinayaki_capabilities': {'site': 'bilibili'}, 'formats': [
            {'quality': 80, 'format': '1080P 高清', 'width': 1920, 'height': 1080,
             'vcodec': 'avc1', 'url': 'one'},
            {'quality': 80, 'format': '1080P 高清', 'width': 1920, 'height': 1080,
             'vcodec': 'hevc', 'url': 'two'},
            {'quality': 116, 'format': '1080P 60帧', 'width': 1920, 'height': 1080,
             'fps': 60, 'vcodec': 'avc1', 'url': 'three'},
        ]}
        self.assertEqual([(item['id'], item['label']) for item in quality_choices(data)], [
            ('bili-q116', '1080P 60帧'), ('bili-q80', '1080P 高清')])
        self.assertEqual(display_label('  1080P   高码率  '), '1080P 高码率')

    def test_bilibili_repairs_corrupted_windows_labels_from_quality_code(self):
        data = {'_rinayaki_capabilities': {'site': 'bilibili'}, 'formats': [
            {'quality': 116, 'format': '1080P ��', 'height': 1080, 'fps': 60,
             'vcodec': 'avc1', 'url': 'one'},
            {'quality': 112, 'format': '1080P ���', 'height': 1080,
             'vcodec': 'avc1', 'url': 'two'},
        ]}
        self.assertEqual([(item['id'], item['label']) for item in quality_choices(data)], [
            ('bili-q116', '1080P 60帧'), ('bili-q112', '1080P 高码率')])


if __name__ == '__main__':
    unittest.main()
