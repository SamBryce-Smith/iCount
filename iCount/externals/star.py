"""
STAR aligner
------------

Interface to running STAR.
"""

import os
import sys
import logging
import subprocess

from threading import Thread
from queue import Queue, Empty

import iCount

LOGGER = logging.getLogger(__name__)


def _execute(cmd):
    """
    Iterator giving stdout and stderr in realtime when executing the cmd.
    """

    def readline_output(out, queue, name):
        for line in iter(out.readline, ''):
            queue.put((name, line))
        out.close()
        queue.put((name, 'readline_output finished.'))

    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True)

    q = Queue()
    t1 = Thread(target=readline_output, args=(popen.stdout, q, 'stdout'), daemon=True).start()
    t2 = Thread(target=readline_output, args=(popen.stderr, q, 'stderr'), daemon=True).start()

    done = 0
    while True:
        out, message = q.get()
        if message == 'readline_output finished.':
            done += 1
        else:
            yield ('{}_line'.format(out), message)

        if done >= 2:
            break

    yield ('return_code', popen.wait())


def get_version():
    args = ['STAR', '--version']
    try:
        ver = subprocess.check_output(args, shell=False,
                                      universal_newlines=True)
        return str(ver).rstrip('\n\r')
    except:
        return None


def build_index(genome_fname, outdir, annotation='', overhang=100, overhang_min=8, threads=1):
    """
    Call STAR to generate genome index, which is used for mapping.

    Parameters
    ----------
    genome_fname : str
        Genome sequence to index.
    outdir : str
        Output folder, where to store genome index.
    annotation : str
        Annotation that defines splice junctions.
    overhang : int
        Sequence length around annotated junctions to be used by STAR when
        constructing splice junction database.
    overhang_min : int
        TODO
    threads : int
        Number of threads that STAR can use for generating index.

    Returns
    -------
    int
        Star return code.

    """
    iCount.log_inputs(LOGGER, level=logging.INFO)

    if not os.path.isdir(outdir):
        raise FileNotFoundError('Output directory does not exist. Make sure it does.')

    LOGGER.info('Building genome index with STAR for genome %s' % genome_fname)
    genome_fname2 = iCount.files.decompress_to_tempfile(
        genome_fname, 'starindex')
    args = [
        'STAR',
        '--runThreadN', '{:d}'.format(threads),
        '--runMode', 'genomeGenerate',
        '--genomeDir', '{:s}'.format(outdir),
        '--genomeFastaFiles', '{:s}'.format(genome_fname2),
        '--alignSJoverhangMin', '{:d}'.format(overhang_min),
    ]
    if annotation:
        annotation2 = iCount.files.decompress_to_tempfile(annotation,
                                                               'starindex')
        args.extend([
            '--sjdbGTFfile', annotation2,
            '--sjdbOverhang', '{:d}'.format(overhang),
        ])
    else:
        annotation2 = annotation

    try:
        ret_code = 1
        for name, value in _execute(args):
            if name == 'return_code' and isinstance(value, int):
                ret_code = value
                break
            elif name == 'stdout_line':
                LOGGER.info(value.strip())
            elif name == 'stderr_lines':
                for line in value.split('\n'):
                    LOGGER.error(line.strip())
    finally:
        # remove temporary decompressed files
        if genome_fname != genome_fname2:
            os.remove(genome_fname2)
        if annotation != annotation2:
            os.remove(annotation2)

    LOGGER.info('Done.')
    return ret_code


def map_reads(sequences_fname, genomedir, outdir, annotation='', multimax=10, mismatches=2,
              threads=1):
    """
    Map FASTQ file reads to reference genome. TODO

    Parameters
    ----------
    sequences_fname : str
        Sequencing reads to map to genome.
    genomedir : str
        Folder with genome index.
    outdir : str
        Output folder, where to store genome index.
    annotation : str
        TODO
    multimax : int
        Number of allowed multiple hits.
    mismatches : int
        Number of allowed mismatches.
    threads : int
        Number of threads that STAR can use for generating index.

    Returns
    -------
    int
        Return code
    """
    iCount.log_inputs(LOGGER, level=logging.INFO)

    if not os.path.isdir(genomedir):
        raise FileNotFoundError('Directory with genome index does not exist. Make sure it does.')
    if not os.path.isdir(outdir):
        raise FileNotFoundError('Output directory does not exist. Make sure it does.')

    LOGGER.info('Mapping reads from %s' % sequences_fname)
    sequences_fname2 = iCount.files.decompress_to_tempfile(
        sequences_fname, 'starmap')

    args = [
        'STAR',
        '--runMode', 'alignReads',
        '--runThreadN', '{:d}'.format(threads),
        '--genomeDir', '{:s}'.format(genomedir),
        '--readFilesIn', '{:s}'.format(sequences_fname2),
    ]
    if not outdir.endswith('/'):
        outdir += '/'

    args.extend([
        '--outFileNamePrefix', '{:s}'.format(outdir),
        '--outSAMprimaryFlag', 'AllBestScore',
        '--outFilterMultimapNmax', '{:d}'.format(multimax),
        '--outFilterMismatchNmax', '{:d}'.format(mismatches),
        '--alignEndsType', 'EndToEnd',
        # otherwise soft-clipping of the starts and ends may produce too
        # many multiple hits
        '--outSAMtype', 'BAM', 'SortedByCoordinate',
        '--outSAMunmapped', 'Within', 'KeepPairs',
    ])
    if annotation:
        annotation2 = iCount.files.decompress_to_tempfile(annotation,
                                                               'starmap')
        args.extend([
            '--sjdbGTFfile', annotation,
        ])
    else:
        annotation2 = annotation

    try:
        ret_code = 1
        for name, value in _execute(args):
            if name == 'return_code' and isinstance(value, int):
                ret_code = value
                break
            elif name == 'stdout_line':
                LOGGER.info(value.strip())
            elif name == 'stderr_lines':
                for line in value.split('\n'):
                    LOGGER.error(line.strip())
    finally:
        # remove temporary decompressed files
        if sequences_fname != sequences_fname2:
            os.remove(sequences_fname2)
        if annotation != annotation2:
            os.remove(annotation2)

    LOGGER.info('Done.')
    return ret_code
