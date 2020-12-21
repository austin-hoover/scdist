"""
The lattice tunes in PyORBIT may be slightly different than those input to the
MADX file. This program adjusts the input tunes to MADX until the output tunes
from PyORBIT are correct.

To run: `./START.sh convert.py 1`
"""

# Standard
import sys
import fileinput
import subprocess
# Third party
import numpy as np
from scipy.optimize import least_squares
# PyORBIT
from orbit.teapot import teapot, TEAPOT_Lattice, TEAPOT_MATRIX_Lattice
from bunch import Bunch
from orbit.utils import helper_funcs as hf


def replace_tunes(script, nux_madx=1.0, nuy_madx=1.0):
    """Replace tunes in madx script."""
    for line in fileinput.input([script], inplace=True):
        text = line.strip()
        if text.startswith('QH:='):
            line = 'QH:={};\n'.format(nux_madx)
        elif text.startswith('QV:='):
            line = 'QV:={};\n'.format(nuy_madx)
        sys.stdout.write(line)
        
        
def set_output_file(script, latfile):
    """Set the output lattice file name in madx script."""
    prefix = 'SAVE,sequence=RNGINJ, FILE='
    new_line = ''.join([prefix, "'{}',clear;\n".format(latfile)])
    for line in fileinput.input([script], inplace=True):
        if line.strip().startswith(prefix):
            line = new_line
        sys.stdout.write(line)
        
        
def run_madx(script, hide_output=True):
    """Run madx script."""
    cmd = './madx {} > /dev/null 2>&1' if hide_output else './madx {}'
    subprocess.call(cmd.format(script), shell=True)
            
            
def get_tunes(file, seq, fringe=False):
    """Create PyORBIT lattice from file and calculate the tunes."""
    lattice = hf.lattice_from_file(file, seq, fringe)
    nux, nuy = hf.get_tunes(lattice, mass=0.93827231, energy=1.0)
    return nux, nuy
           
           
def madx_to_pyorbit_tunes(madx_script, nux_true, nuy_true, latfile, latseq,
                          atol, rtol=1e-4, seed=None):
    """Find correct MADX tunes for desired PyORBIT tunes.
    
    The input tunes to madx are iteratively corrected until the correct
    value in PyORBIT is reached.
    
    Parameters
    ----------
    madx_script : str
        Name of madx script which generates lattice.
    nux_true{nuy_true} : float
        The desired horizontal{vertical} tune.
    latfile : str
        The name of the lattice file output by the MADX script.
    latseq : str
        The name of the `sequence` keyword in the MADX script.
    atol : float
        Tolerance for absolute difference b/w MADX and PyORBIT tunes.
    rtol : float
        Tolerance for absolute relative difference between input tunes on
        subsequent iterations.
        
    Returns
    -------
    nux_madx, nuy_madx: The horizontal and vertical tunes to input to madx.
    error_x, error_y: The differences between target and actual tunes.
    """
    set_output_file(madx_script, latfile)
    
    nux_madx, nuy_madx = nux_true, nuy_true
    converged_x = converged_y = False
    max_iters = 1000
    for _ in range(max_iters):
        replace_tunes(madx_script, nux_madx, nuy_madx)
        run_madx(madx_script)
        nux_calc, nuy_calc = get_tunes(latfile, latseq, fringe=False)
        print 'MADX tunes:    {}, {}'.format(nux_madx, nuy_madx)
        print 'PyORBIT tunes: {}, {}'.format(nux_calc, nuy_calc)
        print ''
        error_x = (nux_true % 1) - nux_calc
        error_y = (nuy_true % 1) - nuy_calc
        converged_x = abs(error_x) < atol or abs(error_x/nux_true) < rtol
        converged_y = abs(error_y) < atol or abs(error_y/nuy_true) < rtol
        if not converged_x:
            nux_madx += error_x
        if not converged_y:
            nuy_madx += error_y
        if converged_x and converged_y:
            return nux_madx, nuy_madx, error_x, error_y


# Settings
nux_true = 6.18
nuy_true = 6.18
atol = 1e-3
madx_script = 'SNSring_madx.mad'
latfile = 'LATTICE.lat'
latseq = 'rnginj'

# Remove old output
subprocess.call('rm ./_output/*', shell=True)

# Find correct madx inputs
nux_madx, nuy_madx, error_x, error_y = madx_to_pyorbit_tunes(
    madx_script, nux_true, nuy_true, latfile, latseq, atol
)
print 'MADX tunes:'
print '    nux_madx = {:.4e}'.format(nux_madx)
print '    nuy_madx = {:.4e}'.format(nuy_madx)
print '    error_x = {:.2e}'.format(error_x)
print '    error_y = {:.2e}'.format(error_y)

# Save lattice file and correct inputs
file = open('./_output/madx_to_pyorbit.dat', 'w')
file.write('MADX tunes: \n')
file.write('    nux_madx = {}\n'.format(nux_madx))
file.write('    nuy_madx = {}\n'.format(nuy_madx))
file.close()
subprocess.call('mv LATTICE.lat ./_output', shell=True)
subprocess.call('mv madx.ps optics optics_for_G4BL twiss ./_output',
                shell=True)
