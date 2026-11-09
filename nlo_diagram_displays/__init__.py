"""Enable --no_open / --merge / directory output for NLO diagram displays.

MG5aMC 3.8.x added these options for LO displays (PR #398). The aMC@NLO
interface still rejects them and cannot merge born/real/loop diagrams into a
single PDF. This plugin ports the NLO side of PR #482 without patching MG5.

Only ``display diagrams`` and ``display diagrams_text`` at NLO are changed;
everything else is dispatched to the stock interfaces.
"""

import logging
import os
import pydoc
import subprocess
import sys
import time
from os.path import join as pjoin

import madgraph.core.base_objects as base_objects
import madgraph.core.diagram_generation as diagram_generation
import madgraph.core.drawing as draw_lib
import madgraph.iolibs.drawing_eps as draw
import madgraph.interface.madgraph_interface as mg_interface
from madgraph.interface.master_interface import MasterCmd

logger = logging.getLogger('cmdprint')

# PR #398 landed in 3.8.0. Without its parsers there is nothing to enable.
_parser = getattr(mg_interface, '_draw_parser', None)
if _parser is None or not any(
        opt.get_opt_string() == '--no_open' for opt in _parser.option_list):
    raise RuntimeError(
        'nlo_diagram_displays requires MG5aMC >= 3.8.0 (PR #398 added '
        '--no_open/--merge to display diagrams). Older releases have no '
        '_draw_parser and cannot run this plugin.')


class NLODiagramDisplaysInterface(MasterCmd):
    """Keep the NLO/LO switcher, override only the two NLO display commands."""

    def do_display(self, line, *args, **opts):
        cmd_args = self.split_arg(line)
        if self.current_interface != 'aMC@NLO' or not cmd_args or \
                cmd_args[0] not in ('diagrams', 'diagrams_text'):
            return super(NLODiagramDisplaysInterface, self).do_display(
                line, *args, **opts)
        self._nlo_check_display(cmd_args)
        return self._nlo_do_display(cmd_args)

    # ------------------------------------------------------------------
    # NLO-only handlers. Prefixed so stock LO/loop behaviour is untouched.
    # ------------------------------------------------------------------
    def _nlo_check_display(self, args):
        """Validate, but do not reject --no_open / --merge like CheckFKS does."""
        mg_interface.MadGraphCmd.check_display(self, args)

        # Drawing controls and flags must not be mistaken for a diagram type
        # or for the output directory.
        alias = {'-no_open': '--no_open', '-merge': '--merge'}
        if args[0] == 'diagrams':
            positional = mg_interface._draw_parser.parse_args(
                [alias.get(a, a) for a in args[1:]])[1]
        else:
            positional = mg_interface._display_text_parser.parse_args(
                [alias.get(a, a) for a in args[1:]])[1]

        if len(positional) >= 2 and \
                positional[0] not in ('born', 'loop', 'virt', 'real'):
            raise self.InvalidCmd(
                'Can only display born, loop (virt) or real diagrams, not %s.'
                % positional[0])

    def _nlo_do_display(self, args):
        get_amps_dict = {
            'real': self._fks_multi_proc.get_real_amplitudes,
            'born': self._fks_multi_proc.get_born_amplitudes,
            'loop': self._fks_multi_proc.get_virt_amplitudes}

        if args[0] == 'diagrams':
            dtype, rest = self._nlo_split_diagram_type(args)
            if dtype:
                key = 'loop' if dtype == 'virt' else dtype
                self._curr_amps = self._nlo_get_displayed_amps(
                    get_amps_dict[key], key)
                if not self._curr_amps:
                    self._curr_amps = diagram_generation.AmplitudeList()
                    return
            dirpath, no_open, merge = self._nlo_parse_display_output_args(
                rest, mg_interface._draw_parser)
            if merge and dirpath is None:
                raise self.InvalidCmd(
                    '--merge requires an explicit directory path, '
                    'e.g. display diagrams ./ --merge')
            eps_files = []
            if dtype:
                eps_files += self._nlo_draw(' '.join(rest), Dtype=key,
                                            do_merge=False)
            else:
                for diag_type, get_amps in get_amps_dict.items():
                    self._curr_amps = get_amps()
                    if self._curr_amps:
                        eps_files += self._nlo_draw(' '.join(rest),
                                                   Dtype=diag_type,
                                                   do_merge=False)
            if merge and eps_files:
                self._nlo_merge_diagrams_eps(dirpath, eps_files, no_open)
            self._curr_amps = diagram_generation.AmplitudeList()
            return

        # diagrams_text
        dtype, rest = self._nlo_split_diagram_type(args)
        if dtype:
            key = 'loop' if dtype == 'virt' else dtype
            self._curr_amps = self._nlo_get_displayed_amps(
                get_amps_dict[key], key)
            if not self._curr_amps:
                self._curr_amps = diagram_generation.AmplitudeList()
                return
        dirpath, no_open, merge = self._nlo_parse_display_output_args(rest)
        if dirpath is None and (no_open or merge):
            raise self.InvalidCmd(
                '--no_open and --merge require an explicit directory path, '
                'e.g. display diagrams_text ./ --no_open')
        text = None
        if dtype:
            text = '\n'.join(amp.nice_string() for amp in self._curr_amps)
            if dirpath:
                self._nlo_write_diagrams_text_files(
                    dirpath, merge=merge, prefix=key + '_')
        else:
            text = 'Born diagrams:\n'
            text += '\n'.join(amp.nice_string()
                              for amp in get_amps_dict['born']())
            text += '\n\nReal diagrams:\n'
            text += '\n'.join(amp.nice_string()
                              for amp in get_amps_dict['real']())
            text += '\n\nLoop diagrams:\n'
            text += '\n'.join(amp.nice_string()
                              for amp in get_amps_dict['loop']())
            if dirpath:
                txt_files = []
                for diag_type, get_amps in get_amps_dict.items():
                    self._curr_amps = get_amps()
                    if self._curr_amps:
                        txt_files += self._nlo_write_diagrams_text_files(
                            dirpath, prefix=diag_type + '_')
                if merge and txt_files:
                    self._nlo_merge_diagrams_text_files(dirpath, txt_files)
        if not no_open:
            pydoc.pager(text)
        self._curr_amps = diagram_generation.AmplitudeList()

    def _nlo_get_displayed_amps(self, get_amps, dtype, kind='diagrams'):
        """Return the requested amplitudes, printing a skip message if empty."""
        amps = get_amps()
        if not amps:
            name = 'virt' if dtype == 'loop' else dtype
            if kind == 'processes':
                logger.info('No "%s" processes exist. Skipping ...' % name)
            else:
                logger.info('No "%s" diagrams exist for this process. '
                            'Skipping ...' % name)
        return amps

    @staticmethod
    def _nlo_split_diagram_type(args):
        """Remove an optional born/real/virt/loop selector from the arguments."""
        for i, arg in enumerate(args[1:], 1):
            if arg in ('born', 'real', 'virt', 'loop'):
                return ('virt' if arg == 'loop' else arg), \
                    args[1:i] + args[i + 1:]
        return None, args[1:]

    def _nlo_parse_display_output_args(self, line_args, parser=None):
        """Return (directory, no_open, merge), creating the directory if needed."""
        parser = parser or mg_interface._display_text_parser
        alias = {'-no_open': '--no_open', '-merge': '--merge'}
        (options, args) = parser.parse_args(
            [alias.get(a, a) for a in line_args])
        if len(args) > 1:
            raise self.InvalidCmd('Too many arguments: %s' % ' '.join(args))
        if not args:
            return None, options.no_open, options.merge
        if not os.path.isdir(args[0]):
            try:
                os.makedirs(args[0], exist_ok=True)
            except OSError as e:
                raise self.InvalidCmd(
                    'Cannot create output directory %s: %s' % (args[0], str(e)))
        return args[0], options.no_open, options.merge

    def _nlo_write_diagrams_text_files(self, dirpath, merge=False, prefix=''):
        """Write one text file per amplitude, optionally merged."""
        amplitudes = diagram_generation.AmplitudeList()
        for amp in self._curr_amps:
            amplitudes.extend(amp.get_amplitudes())

        txt_files = []
        for amp in amplitudes:
            filename = pjoin(
                dirpath, 'diagrams_' + prefix +
                amp.get('process').shell_string() + '.txt')
            with open(filename, 'w') as fs:
                fs.write(amp.nice_string())
            logger.info('Wrote file ' + filename)
            txt_files.append(filename)

        if merge and txt_files:
            self._nlo_merge_diagrams_text_files(dirpath, txt_files)
        return txt_files

    def _nlo_merge_diagrams_text_files(self, dirpath, txt_files):
        """Concatenate the text files into all_diagrams_text.txt."""
        merged_file = pjoin(dirpath, 'all_diagrams_text.txt')
        try:
            with open(merged_file, 'w') as out_fs:
                for f in sorted(txt_files):
                    with open(f, 'r') as in_fs:
                        out_fs.write(in_fs.read())
                        out_fs.write('\n\n')
            logger.info('Merged diagrams text into ' + merged_file)
        except IOError as e:
            logger.warning('Failed to merge text files: %s' % str(e))

    def _nlo_merge_diagrams_eps(self, dirpath, eps_files, no_open=False):
        """Merge the EPS files into all_diagrams.pdf."""
        output_pdf = pjoin(dirpath, 'all_diagrams.pdf')
        eps_files_sorted_abs = sorted(os.path.abspath(f) for f in eps_files)
        gs_cmd = ['gs', '-dBATCH', '-dNOPAUSE', '-q', '-sDEVICE=pdfwrite',
                  '-sOutputFile=' + os.path.abspath(output_pdf)] + eps_files_sorted_abs
        try:
            subprocess.check_call(gs_cmd, shell=False)
        except (subprocess.CalledProcessError, OSError) as e:
            logger.warning('Failed to merge diagrams into PDF with '
                           'ghostscript: %s' % str(e))
            logger.warning("Make sure 'gs' (ghostscript) is installed and "
                           'available in PATH.')
        else:
            logger.info('Merged diagrams into ' + output_pdf)
            if not no_open:
                self.exec_cmd('open %s' % output_pdf)

    # ------------------------------------------------------------------
    # Drawing helper, used only by the NLO handler. Stock draw() is left
    # untouched, so LO and loop-induced displays keep their exact behaviour.
    # Additions over stock: a per-type filename prefix (born and loop files
    # otherwise overwrite each other), a suppressible merge, and the list
    # of EPS files so all three NLO types can be merged into one PDF.
    # ------------------------------------------------------------------
    def _nlo_draw(self, line, selection='all', Dtype='', do_merge=True):
        """Draw the Feynman diagrams for the current amplitudes."""
        args = self.split_arg(line)
        alias = {'-no_open': '--no_open', '-merge': '--merge'}
        args = [alias.get(a, a) for a in args]
        (parsed_opts, args) = mg_interface._draw_parser.parse_args(args)
        no_open = parsed_opts.no_open
        merge = do_merge and parsed_opts.merge

        if not args:
            if no_open:
                raise self.InvalidCmd(
                    '--no_open requires an explicit directory path, '
                    'e.g. display diagrams ./ --no_open')
            if merge:
                raise self.InvalidCmd(
                    '--merge requires an explicit directory path, '
                    'e.g. display diagrams ./ --merge')
        elif not os.path.isdir(args[0]):
            try:
                os.makedirs(args[0], exist_ok=True)
            except OSError as e:
                raise self.InvalidCmd(
                    'Cannot create output directory %s: %s' % (args[0], str(e)))

        self.check_draw(args)

        if any(isinstance(a, diagram_generation.DecayChainAmplitude)
               for a in self._curr_amps) and not self._done_export:
            logger.warning('WARNING: You try to draw decay chain diagrams '
                           'without first running output.\n'
                           '\t  The decay processes will be drawn separately')

        if draw.EpsDiagramDrawer.april_fool:
            parsed_opts.horizontal = True
            parsed_opts.external = True
            parsed_opts.max_size = 0.3
            parsed_opts.add_gap = 0.5
        options = draw_lib.DrawOption(parsed_opts)
        start = time.time()

        amplitudes = diagram_generation.AmplitudeList()
        for amp in self._curr_amps:
            amplitudes.extend(amp.get_amplitudes())

        eps_files = []
        # Loop amplitudes carry the born process: keep the diagram type in the
        # name so born and loop files do not overwrite each other.
        prefix = (Dtype + '_') if Dtype else ''
        for amp in amplitudes:
            filename = pjoin(args[0], 'diagrams_' + prefix +
                             amp.get('process').shell_string() + '.eps')
            eps_files.append(filename)

            if selection == 'all' and Dtype != 'loop':
                diags = amp.get('diagrams')
            elif selection == 'born':
                diags = amp.get('born_diagrams')
            elif selection == 'loop' or Dtype == 'loop':
                diags = base_objects.DiagramList(
                    [d for d in amp.get('loop_diagrams')
                     if d.get('type') > 0])
                if len(diags) > 5000:
                    logger.warning('Displaying only the first 5000 diagrams')
                    diags = base_objects.DiagramList(diags[:5000])

            plot = draw.MultiEpsDiagramDrawer(
                diags, filename, model=self._curr_model, amplitude=amp,
                legend=amp.get('process').input_string(), diagram_type=Dtype)
            logger.info('Drawing ' + amp.get('process').nice_string())
            plot.draw(opt=options)
            logger.info('Wrote file ' + filename)
            if not no_open:
                self.exec_cmd('open %s' % filename)

        if merge and eps_files:
            self._nlo_merge_diagrams_eps(args[0], eps_files, no_open)

        logger.info('time to draw %s' % (time.time() - start))
        return eps_files


new_interface = NLODiagramDisplaysInterface
minimal_mg5amcnlo_version = (3, 8, 0)
maximal_mg5amcnlo_version = (3, 9, 99)
latest_validated_version = (3, 8, 1)
