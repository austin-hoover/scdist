"""Track a coasting beam through a symmetric FODO lattice. 

The bunch coordinates and transverse covariance matrix are saved after each 
cell.
"""
import sys
import numpy as np
from scipy import optimize as opt
from tqdm import trange

from bunch import Bunch
from spacecharge import SpaceChargeCalc2p5D
from orbit.diagnostics import BunchMonitorNode
from orbit.space_charge.sc2p5d.scLatticeModifications import setSC2p5DAccNodes
from orbit.envelope import DanilovEnvelope
from orbit.space_charge.envelope import DanilovEnvSolverNode
from orbit.space_charge.envelope import set_env_solver_nodes
from orbit.space_charge.envelope import set_perveance
from orbit.teapot import teapot
from orbit.teapot import TEAPOT_Lattice
from orbit.twiss import twiss
from orbit.utils import helper_funcs as hf

# Local
from matching import Matcher

    
# Settings
#------------------------------------------------------------------------------
# Lattice
mu_x0 = 90.0  # horizontal tune [deg]
mu_y0 = 80.0  # vertical tune [deg]
cell_length = 5.0  # [m]
n_cells = 100

# Initial bunch
n_parts = 256000  # number of macro particles
mass = 0.93827231  # particle mass [GeV/c^2]
kin_energy = 1.0  # particle kinetic energy [GeV/c^2]
bunch_length = 200.0 # [m]
eps_x = 20e-6  # [m rad]
eps_y = 20e-6  # [m rad]
mu_x = 45.0  # depressed horizontal tune [deg]
mu_y = 45.0  # depressed vertical tune [deg]
bunch_kind = 'danilov22'  # {'kv', 'gaussian', 'waterbag', 'danilov22'}

# Space charge solver
max_solver_spacing = 0.075 # [m]
min_solver_spacing = 1e-6 # [m]
gridpts = (128, 128, 1) # (x, y, z)


# Generate rms matched distribution
# ------------------------------------------------------------------------------
lattice = hf.fodo_lattice(mu_x0, mu_y0, cell_length, fill_fac=0.5, start='quad')
lattice.set_fringe(False)
matcher = Matcher(lattice, kin_energy, eps_x, eps_y)

print 'Setting depressed KV tunes.'
perveance = matcher.set_tunes(mu_x, mu_y, verbose=2)
intensity = hf.get_intensity(perveance, mass, kin_energy, bunch_length)
print 'Matched KV beam:'
print '    Perveance = {:.3e}'.format(perveance)
print '    Intensity = {:.3e}'.format(intensity)
print '    Zero-current tunes:', mu_x0, mu_y0
print '    Depressed tunes:', matcher.tunes()

print 'Generating bunch.'
if bunch_kind != 'danilov22':
    kws = dict()
    if bunch_kind == 'gaussian':
        kws['cut_off'] = 3.0
    bunch, params_dict = hf.coasting_beam(
        bunch_kind, 
        n_parts, 
        matcher.twiss(), 
        (eps_x, eps_y), 
        bunch_length, 
        mass, 
        kin_energy, 
        intensity, 
        **kws
    )
else:
    mode = 1
    env = DanilovEnvelope(eps_x + eps_y, mode, eps_x/(eps_x+eps_y), mass, kin_energy, length=bunch_length)
    env.match_bare(lattice, '2D')
    env.set_intensity(intensity)
    env_solver_nodes = set_env_solver_nodes(lattice, env.perveance, max_solver_spacing)
    print('Matching Danilov {2, 2} distribution.')
    env.match(lattice, env_solver_nodes, verbose=2)
    bunch, params_dict = env.to_bunch(n_parts, no_env=True)

# Add space charge nodes
lattice = hf.fodo_lattice(mu_x0, mu_y0, cell_length, fill_fac=0.5, start='quad')
lattice.set_fringe(False)
lattice.split(max_solver_spacing)    
calc2p5d = SpaceChargeCalc2p5D(*gridpts)
sc_nodes = setSC2p5DAccNodes(lattice, min_solver_spacing, calc2p5d)

# Add monitor node
monitor_node = BunchMonitorNode(mm_mrad=True, transverse_only=True)
hf.add_node_at_start(lattice, monitor_node)

print 'Tracking bunch.'
for _ in trange(n_cells):
    lattice.trackBunch(bunch, params_dict)

# Save data
print 'Saving bunch coordinates.'
np.save('_output/data/coords.npy', monitor_node.get_data())
