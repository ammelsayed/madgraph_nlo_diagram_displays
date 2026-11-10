import os
import shutil
import tempfile
import unittest
from unittest import mock

from madgraph import InvalidCmd
from nlo_diagram_displays import NLODiagramDisplaysInterface


class TestNLODiagramDisplays(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cmd = NLODiagramDisplaysInterface()

    def do(self, line):
        self.cmd.exec_cmd(line)

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_lo_display_untouched(self):
        """LO displays keep stock behaviour (no --no_open rejection)."""
        self.do('import model sm')
        self.do('generate e+ e- > e+ e-')
        self.do('display diagrams . --no_open')
        self.assertTrue(any(f.startswith('diagrams_') and f.endswith('.eps')
                            for f in os.listdir(self.tmpdir)))

    def test_nlo_display_merge(self):
        """NLO diagrams accept --no_open/--merge and produce one PDF."""
        if not shutil.which('gs'):
            self.skipTest('ghostscript not installed')
        self.do('import model loop_sm')
        self.do('generate p p > t t~ [QCD]')
        outdir = os.path.join(self.tmpdir, 'diags')
        self.do('display diagrams %s --no_open --merge' % outdir)
        files = os.listdir(outdir)
        eps = [f for f in files if f.endswith('.eps')]
        self.assertTrue(eps, files)
        # born and loop files must not overwrite each other
        self.assertTrue(any(f.startswith('diagrams_born_') for f in eps), eps)
        self.assertTrue(any(f.startswith('diagrams_loop_') for f in eps), eps)
        pdf = os.path.join(outdir, 'all_diagrams.pdf')
        self.assertTrue(os.path.isfile(pdf), files)
        with open(pdf, 'rb') as handle:
            self.assertEqual(handle.read(4), b'%PDF')
        self.assertGreater(os.path.getsize(pdf), 1000)

    def test_nlo_diagrams_text_merge(self):
        """NLO diagrams_text honours directory, --no_open and --merge."""
        self.do('import model loop_sm')
        self.do('generate p p > t t~ [QCD]')
        outdir = os.path.join(self.tmpdir, 'text')
        self.do('display diagrams_text %s --no_open --merge' % outdir)
        files = os.listdir(outdir)
        txt = [f for f in files if f.endswith('.txt')]
        self.assertTrue(any(f.startswith('diagrams_born_') for f in txt), txt)
        self.assertTrue(any(f.startswith('diagrams_real_') for f in txt), txt)
        self.assertIn('all_diagrams_text.txt', files)
        with open(os.path.join(outdir, 'all_diagrams_text.txt')) as handle:
            self.assertTrue(handle.read().strip())

    def test_nlo_selector_skips_absent_type(self):
        """A selector for a missing amplitude type is skipped, not raised."""
        self.do('import model loop_sm')
        self.do('generate p p > t t~ [QCD]')
        outdir = os.path.join(self.tmpdir, 'virt')
        # Simulate a process with no virtual amplitudes.
        with mock.patch.object(self.cmd._fks_multi_proc,
                               'get_virt_amplitudes', return_value=[]):
            with self.assertLogs('cmdprint', level='INFO') as captured:
                self.cmd.do_display('diagrams virt %s --no_open' % outdir)
        self.assertTrue(any('No "virt" diagrams exist' in m
                            for m in captured.output), captured.output)

    def test_nlo_merge_requires_directory(self):
        """--merge without a directory is rejected with a clear message."""
        self.do('import model loop_sm')
        self.do('generate p p > t t~ [QCD]')
        with self.assertRaises(InvalidCmd) as ctx:
            self.cmd.do_display('diagrams --merge --no_open')
        self.assertIn('--merge requires an explicit directory', str(ctx.exception))

    def test_failed_merge_keeps_old_pdf(self):
        """A failed ghostscript run leaves the previous PDF untouched."""
        self.do('import model loop_sm')
        self.do('generate p p > t t~ [QCD]')
        outdir = os.path.join(self.tmpdir, 'diags')
        os.makedirs(outdir)
        pdf = os.path.join(outdir, 'all_diagrams.pdf')
        with open(pdf, 'wb') as handle:
            handle.write(b'old report')
        with mock.patch('nlo_diagram_displays.subprocess.check_call',
                        side_effect=OSError('ghostscript failed')):
            self.do('display diagrams %s --no_open --merge' % outdir)
        with open(pdf, 'rb') as handle:
            self.assertEqual(handle.read(), b'old report')


if __name__ == '__main__':
    unittest.main()
