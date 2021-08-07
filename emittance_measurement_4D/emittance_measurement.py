"""
Methods for 4D emittance measurement using the quadrupole scan method.
"""
import sys
from datetime import datetime

import numpy as np
from scipy import optimize as opt
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import proplot as plot

from . import utils
from . import plotting as myplt
from . import accphys_utils


DEFAULT_COLORCYCLE = plt.rcParams['axes.prop_cycle'].by_key()['color']


# Helper functions
#-------------------------------------------------------------------------------
def list_to_string(items):
    """Example: [1, 2, 3] -> '1 2 3'."""
    string = ''
    for item in items:
        string += '{} '.format(item)
    return string[:-1]


def string_to_list(string):
    """Convert string to list of floats.
    
    '1 2 3' -> [1.0, 2.0, 3.0])
    """
    return [float(token) for token in string.split()]


# Reconstruction
#-------------------------------------------------------------------------------
def to_mat(sigma):
    """Return covariance matrix from 10 element moment vector."""
    s11, s22, s12, s33, s44, s34, s13, s23, s14, s24 = sigma
    return np.array([[s11, s12, s13, s14], 
                     [s12, s22, s23, s24], 
                     [s13, s23, s33, s34], 
                     [s14, s24, s34, s44]])


def to_vec(Sigma):
    """Return 10 element moment vector from covariance matrix."""
    s11, s12, s13, s14 = Sigma[0, :]
    s22, s23, s24 = Sigma[1, 1:]
    s33, s34 = Sigma[2, 2:]
    s44 = Sigma[3, 3]
    return np.array([s11, s22, s12, s33, s44, s34, s13, s23, s14, s24])


def reconstruct(transfer_mats, moments, **lsq_kws):
    """Reconstruct covariance matrix from wire-scanner data.
    
    Parameters
    ----------
    transfer_mats : list of (4, 4) ndarray, length n
        List of 4x4 transfer matrix at each scan.
    moments : list or ndarray, shape (n, 3)
        List of [<xx>, <yy>, <xy>] moments for each scan.
    **lsq_kws
        Key word arguments passed to scipy.optimize.lsq_linear

    Returns
    -------
    ndarray, shape (4, 4)
        Covariance matrix at reconstruction point.
    """
    A, b = [], []
    for M, (sig_xx, sig_yy, sig_xy) in zip(transfer_mats, moments):
        A.append([M[0, 0]**2, M[0, 1]**2, 2*M[0, 0]*M[0, 1], 0, 0, 0, 0, 0, 0, 0])
        A.append([0, 0, 0, M[2, 2]**2, M[2, 3]**2, 2*M[2, 2]*M[2, 3], 0, 0, 0, 0])
        A.append([0, 0, 0, 0, 0, 0, M[0, 0]*M[2, 2],  M[0, 1]*M[2, 2],  M[0, 0]*M[2, 3],  M[0, 1]*M[2, 3]])
        b.append(sig_xx)
        b.append(sig_yy)
        b.append(sig_xy)
    A, b = np.array(A), np.array(b)
    lb = 10 * [-np.inf]
    lb[0] = lb[1] = lb[3] = lb[4] = 0.0 # Squared moments can't be negative
    ub = 10 * [+np.inf]
    lsq_kws.setdefault('lsq_solver', 'lsmr')
    result = opt.lsq_linear(A, b, bounds=(lb, ub),  **lsq_kws)
    return to_mat(result.x)


def get_sig_xy(sig_xx, sig_yy, sig_uu, diag_wire_angle):
    """Compute cov(x, y) from horizontal, vertical, and diagonal wires.
    
    [To do: Write formula in terms of cov(x, y) in terms of cov(x, x), 
     cov(y, y), and cov(u, u).]
    """
    phi = np.radians(90.0) + diag_wire_angle
    sin, cos = np.sin(phi), np.cos(phi)
    sig_xy = (sig_uu - sig_xx*(cos**2) - sig_yy*(sin**2)) / (2 * sin * cos)
    return sig_xy


# PTA file data processing
#-------------------------------------------------------------------------------
class Stat:
    """Container for a signal parameter.
    
    Attributes
    ----------
    name : str
        Parameter name.
    rms : float
        Parameter value from rms calculation.
    fit : float
        Parameter value from Gaussian fit.
    """
    def __init__(self, name, rms, fit):
        self.name, self.rms, self.fit = name, rms, fit

        
class Signal:
    """Container for profile signal.
    
    Attributes
    ----------
    pos : list
        Wire positions.
    raw : list
        Raw signal amplitudes at each position.
    fit : list
        Gaussian fit amplitudes at each position.
    stats : dict
        Each key is a different statistical parameter: ('Area' or 'Mean' or ...). 
        Each value is a Stat object that holds the parameter name, rms value, 
        and Gaussian fit value.
    """
    def __init__(self, pos, raw, fit, stats):
        self.pos, self.raw, self.fit, self.stats = pos, raw, fit, stats
        
        
class Profile:
    """Stores data from single wire-scanner.
    
    Attributes
    ----------
    hor, ver, dia : Signal
        Signal object for horizontal, vertical and diagonal wire.
    """
    def __init__(self, pos, raw, fit=None, stats=None):
        """Constructor.
        
        Parameters
        ----------
        pos : [xpos, ypos, upos]
            Position lists for each wire.
        raw : [xraw, yraw, uraw]
            List of raw signal amplitudes for each wire.
        fit : [xfit, yfit, ufit]
            List of Gaussian fit amplitudes for each wire.
        stats : [xstats, ystats, ustats]
            List of stats dictionaries for each wire.
        """
        xpos, ypos, upos = pos
        xraw, yraw, uraw = raw
        if fit is None:
            xfit = yfit = ufit = None
        else:
            xfit, yfit, ufit = fit
        if stats is None:
            xstats = ystats = ustats = None
        else:
            xstats, ystats, ustats = stats   
        self.hor = Signal(xpos, xraw, xfit, xstats)
        self.ver = Signal(ypos, yraw, yfit, ystats)
        self.dia = Signal(upos, uraw, ufit, ustats)   
        

class Measurement(dict):
    """A dictionary of profiles for one measurement.
    
    Each measurement is a collection of wire scans at a single machine setting.
    """
    def __init__(self, filename):
        dict.__init__(self)
        self.filename = filename
        self.timestamp = None
        self.profiles = dict()
        self.pvloggerid = None
        self.node_ids = None
        self.read_pta_file()
        
    def read_pta_file(self):
        # Store the timestamp on the file.
        date, time = self.filename.split('WireAnalysisFmt-')[-1].split('_')
        time = time.split('.pta')[0]
        year, month, day = [int(token) for token in date.split('.')]
        hour, minute, second = [int(token) for token in time.split('.')]
        self.timestamp = datetime(year, month, day, hour, minute, second)
        
        # Collect lines corresponding to each wire-scanner
        file = open(self.filename, 'r')
        lines = dict()
        ws_id = None
        for line in file:
            line = line.rstrip()
            if line.startswith('RTBT_Diag'):
                ws_id = line
                continue
            if ws_id is not None:
                lines.setdefault(ws_id, []).append(line)
            if line.startswith('PVLoggerID'):
                self.pvloggerid = int(line.split('=')[1])
        file.close()

        # Read the lines
        profiles = dict()
        self.node_ids = sorted(list(lines))
        for node_id in sorted(list(self.node_ids)):
            # Split lines into three sections:
            #     stats: statistical signal parameters;
            #     raw: wire positions and raw signal amplitudes;
            #     fit: wire positions and Gaussian fit amplitudes.
            # There is one blank line after each section.
            sep = ''
            lines_stats, lines_raw, lines_fit = utils.split(lines[node_id], sep)[:3]

            # Remove headers and dashed lines beneath headers.
            lines_stats = lines_stats[2:]
            lines_raw = lines_raw[2:]
            lines_fit = lines_fit[2:]   

            # The columns of the following array are ['pos', 'yraw', 'uraw', 'xraw', 
            # 'xpos', 'ypos', 'upos']. (NOTE: This is not the order that is written
            # in the file header.)
            data_arr_raw = np.array([string_to_list(line) for line in lines_raw])
            pos, yraw, uraw, xraw, xpos, ypos, upos = data_arr_raw.T

            # This next array is the same, but it contains 'yfit', 'ufit', 'xfit', 
            # instead of 'yraw', 'uraw', 'xraw'.
            data_arr_fit = np.array([string_to_list(line) for line in lines_fit])
            pos, yfit, ufit, xfit, xpos, ypos, upos = data_arr_fit.T

            # Get statistical signal parameters. (Headers don't give true ordering.)
            xstats, ystats, ustats = dict(), dict(), dict()
            for line in lines_stats:
                tokens = line.split()
                name = tokens[0]
                vals = [float(val) for val in tokens[1:]]
                s_yfit, s_yrms, s_ufit, s_urms, s_xfit, s_xrms = vals
                xstats[name] = Stat(name, s_xrms, s_xfit)
                ystats[name] = Stat(name, s_yrms, s_yfit)
                ustats[name] = Stat(name, s_urms, s_ufit)

                
            profile = Profile(
                [xpos, ypos, upos], 
                [xraw, yraw, uraw], 
                [xfit, yfit, ufit], 
                [xstats, ystats, ustats],
            )
            self[node_id] = profile
            
            
def is_harp_file(filename):
    file = open(filename)
    for line in file:
        if 'Harp' in line:
            return True
    return False


def read_pta_harp(filename):
    """Return dictionary of Profiles from PTA harp file.
    
    The dictionary keys are the wire-scanner names.
    """
    file = open(filename, 'r')
    data = []
    for line in file:
        tokens = line.rstrip().split()
        if not tokens or tokens[0] in ['start', 'RTBT_Diag:Harp30', 'PVLoggerID']:
            continue
        data.append([float(token) for token in tokens])
    file.close()
    xpos, xraw, ypos, yraw, upos, uraw = np.array(data).T
    profile = Profile([xpos, ypos, upos], 
                      [xraw, yraw, uraw])
    return profile



# Plotting
#-------------------------------------------------------------------------------
def plot_profiles(measurements, fit=False, kws_raw=None, kws_fit=None, 
                  width=8, vscale=1.4):
    """Plot the beam profiles on each wire.
    
    measurements : list[Measurement]
    fit : bool
        Whether to plot the Gaussian fit.
    kws_raw : dict
        Key word arguments for the profile plot.
    kws_fit : dict
        Key word arguments for the Gaussian fit plot.
    """
    if kws_raw is None:
        kws_raw = dict()
    if kws_fit is None:
        kws_fit = dict()
    kws_raw['legend'] = kws_fit['legend'] = False
    kws_raw.setdefault('marker', '.')
    kws_raw.setdefault('ms', 3)
    kws_raw.setdefault('lw', 0)
    kws_fit.setdefault('color', 'k')
    kws_fit.setdefault('alpha', 0.2)
    kws_fit.setdefault('zorder', 0)
    n_meas = len(measurements)
    fig, axes = plot.subplots(nrows=n_meas, ncols=3, spanx=False, 
                              figsize=(width, vscale*n_meas))
    ws_ids = measurements[0].node_ids
    for i, measurement in enumerate(measurements):
        for ws_id in measurement.node_ids:
            profile = measurement[ws_id]
            axes[i, 0].plot(profile.hor.pos, profile.hor.raw, **kws_raw)
            axes[i, 1].plot(profile.ver.pos, profile.ver.raw, **kws_raw)
            axes[i, 2].plot(profile.dia.pos, profile.dia.raw, **kws_raw)
            if fit:
                axes[i, 0].plot(profile.hor.pos, profile.hor.fit, **kws_fit)
                axes[i, 1].plot(profile.ver.pos, profile.ver.fit, **kws_fit)
                axes[i, 2].plot(profile.dia.pos, profile.dia.fit, **kws_fit)
                
    axes[0, -1].legend(labels=ws_ids, fontsize='small', loc=(1.02, 0), ncols=1)
    axes.format(ylabel='Signal', grid=False, 
                toplabels=['Horizontal', 'Vertical', 'Diagonal'])
    axes[-1, 0].set_xlabel('x [mm]')
    axes[-1, 1].set_xlabel('y [mm]')
    axes[-1, 2].set_xlabel('u [mm]')
    for ax in axes:
        ax.grid(axis='y')
    return axes


def possible_points(transfer_mats, moments, slopes): 
    coords_list = []
    for M, (sig_xx, sig_yy, sig_xy) in zip(transfer_mats, moments):
        Minv = np.linalg.inv(M)
        coords = []
        for slope in slopes:
            vec = [np.sqrt(sig_xx), slope, np.sqrt(sig_yy), slope]
            vec = np.matmul(Minv, vec)
            coords.append(vec)
        coords_list.append(coords)
    return np.array(coords_list)


def rec_lines(ax, transfer_mats, moments, plane='x-xp', norm_mat=None, slopes=None, **plt_kws):
    
    if slopes is None:
        slopes = [-100., 100.]
    
    V = norm_mat
    if V is None:
        V = np.identity(4)
    Vinv = np.linalg.inv(V)
    
    for coords in possible_points(transfer_mats, moments, slopes):
        coords = utils.apply(Vinv, coords)
        if plane == 'x-xp':
            ax.plot(coords[:, 0], coords[:, 1], **plt_kws)
        elif plane == 'y-yp':
            ax.plot(coords[:, 2], coords[:, 3], **plt_kws)
    return ax


def reconstruction_lines(ax, transfer_mats_dict, moments_dict, plane='x-xp', norm_mat=None, 
                         slopes=None, legend=False, legend_kws=None, **plt_kws):
        
    plt_kws.setdefault('lw', 0.75)
        
    if legend_kws is None:
        legend_kws = dict()
    legend_kws.setdefault('fontsize', 'small')
    legend_kws.setdefault('loc', (1.03, 0.0))
    legend_kws.setdefault('ncol', 1)
    
    ws_ids = sorted(list(transfer_mats_dict))
    colors = DEFAULT_COLORCYCLE[:len(ws_ids)]
    for ws_id, color in zip(ws_ids, colors):
        rec_lines(ax, transfer_mats_dict[ws_id], moments_dict[ws_id], 
                  plane, norm_mat, slopes, color=color, **plt_kws)
    if legend:
        lines = [Line2D([0], [0], color=color) for color in colors]
        ax.legend(lines, ws_ids, **legend_kws)