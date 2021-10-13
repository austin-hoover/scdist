"""Transport a beam through the RTBT and store the coordinates at the wire-scanners/target."""
from __future__ import print_function
import sys
from pprint import pprint

import numpy as np
import scipy.optimize as opt
from tqdm import tqdm
from tqdm import trange

from bunch import Bunch
from foil import Foil
from impedances import LImpedance
from impedances import TImpedance
from spacecharge import LSpaceChargeCalc
from spacecharge import Boundary2D
from spacecharge import SpaceChargeCalc2p5D
from spacecharge import SpaceChargeCalcSliceBySlice2D
from orbit.collimation import TeapotCollimatorNode
from orbit.collimation import addTeapotCollimatorNode
from orbit.diagnostics import BunchMonitorNode
from orbit.diagnostics import BunchStatsNode
from orbit.diagnostics import analysis
from orbit.diagnostics import add_analysis_node
from orbit.diagnostics import addTeapotDiagnosticsNode
from orbit.diagnostics import StatLats, Moments
from orbit.diagnostics import TeapotStatLatsNode
from orbit.diagnostics import TeapotMomentsNode
from orbit.diagnostics import TeapotTuneAnalysisNode
from orbit.diagnostics import addTeapotStatLatsNodeSet
from orbit.diagnostics import addTeapotMomentsNodeSet
from orbit.envelope import DanilovEnvelope
from orbit.foils import TeapotFoilNode
from orbit.foils import addTeapotFoilNode
from orbit.impedances import addImpedanceNode
from orbit.impedances import LImpedance_Node
from orbit.impedances import FreqDep_LImpedance_Node
from orbit.impedances import BetFreqDep_LImpedance_Node
from orbit.impedances import TImpedance_Node
from orbit.impedances import FreqDep_TImpedance_Node
from orbit.impedances import BetFreqDep_TImpedance_Node
from orbit.injection import TeapotInjectionNode
from orbit.injection import addTeapotInjectionNode
from orbit.injection import InjectParts
from orbit.injection import JohoTransverse
from orbit.injection import JohoLongitudinal
from orbit.injection import SNSESpreadDist
from orbit.injection import UniformLongDist
from orbit.lattice import AccNode
from orbit.rf_cavities import RFNode, RFLatticeModifications
from orbit.space_charge.envelope import set_env_solver_nodes
from orbit.space_charge.sc1d import addLongitudinalSpaceChargeNode
from orbit.space_charge.sc1d import SC1D_AccNode
from orbit.space_charge import sc2p5d
from orbit.space_charge import sc2dslicebyslice
from orbit.teapot import teapot
from orbit.teapot import TEAPOT_Lattice
from orbit.teapot import DriftTEAPOT
from orbit.time_dep import time_dep
from orbit.time_dep.waveforms import SquareRootWaveform
from orbit.time_dep.waveforms import ConstantWaveform
from orbit.time_dep.waveforms import LinearWaveform
from orbit.utils import helper_funcs as hf
from orbit.utils.consts import speed_of_light
from orbit.utils.general import load_stacked_arrays
from orbit.utils.general import save_stacked_array
from orbit.utils.general import delete_files_not_folders

# Local
from helpers import get_traj
from helpers import get_part_coords
from helpers import InjRegionController


# Settings
madx_file = '_input/SNSring_nux6.18_nuy6.18_foilinbend.lat'
madx_seq = 'rnginj'
kin_energy = 0.8 # [GeV]
mass = 0.93827231 # [GeV/c^2]


# Lattice setup
ring = time_dep.TIME_DEP_Lattice()
ring.readMADX(madx_file, madx_seq)
ring.set_fringe(False)
ring.initialize()
ring = hf.get_sublattice(ring, None, 'rtbt_start')
        
        
print('Loading bunch coordinates.')
coords = load_stacked_arrays('_saved/fringe_included/init(0,0,0,0)_final(21,0,0,1.1)_500turns_intensityperturn=1.5e11_fringe=ON_sol=OFF_lsc=ON_tsc=sliced_timp=OFF_limp=ON_rf=5.03kV-6.07kV_E=0.8GeV_bleng=30-64_500Kparts/data/coords.npz')

turns = [0, 99, 199, 299, 399, 499]

coords_new = []
for turn in turns:
    X = coords[turn]
    X[:, :4] *= 0.001
    bunch, params_dict = hf.initialize_bunch(mass, kin_energy)
    for (x, xp, y, yp, z, dE) in X:
        bunch.addParticle(x, xp, y, yp, z, dE)

    print('Tracking bunch at turn {} to RTBT entrance.'.format(turn))
    ring.trackBunch(bunch, params_dict)

    X = analysis.bunch_coord_array(bunch)
    coords_new.append(np.copy(X))

print('Saving bunch coordinates.')
save_stacked_array('_output/scratch/coords_new.npz', coords_new)

