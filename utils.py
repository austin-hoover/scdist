# Standard
import os
# Third party
import numpy as np
import numpy.linalg as la
import pandas as pd
from sympy import pprint, Matrix
from scipy.integrate import trapz
from IPython.display import display, HTML


# General functions
#------------------------------------------------------------------------------
def list_files(dir):
    """List all files in directory not starting with '.'"""
    files = os.listdir(dir)
    return [file for file in files if not file.startswith('.')]
    

def is_empty(dir):
    """Return True if directory is empty."""
    return len(list_files(dir)) > 0
    
    
def delete_files_not_folders(dir):
    """Delete all files in directory and subdirectories."""
    for root, dirs, files in os.walk(dir):
        for file in files:
            if not file.startswith('.'):
                os.remove(os.path.join(root, file))
                
               
def file_exists(file):
    """Return True if the file exists."""
    return os.path.isfile(file)
    
    
def merge_lists(x, y):
    """Returns [x[0], y[0], ..., x[-1], y[-1]]"""
    return [x for pair in zip(a, b) for x in pair]
    
    
def merge_dicts(*dictionaries):
    """Given any number of dictionaries, shallow copy and merge into a new dict.
    
    Precedence goes to key value pairs in latter dictionaries. This function
    will work in Python 2 or 3. Note that in version 3.5 or greater we can just
    call `z = {**x, **y}`, and in 3.9 we can call `z = x | y`, to merge two
    dictionaries (with the values of y replacing those in x).
    
    Example usage:
        >> w = dict(a=1, b=2, c=3)
        >> x = dict(e=4, f=5, c=6)
        >> y = dict(g=7, h=8, f=7)
        >> merge_dicts(w, x, y)
        >> {'a': 1, 'b': 2, 'c': 6, 'e': 4, 'f': 7, 'g': 7, 'h': 8}
    
    Copied from the accepted answer here:'https://stackoverflow.com/questions/
    /38987/how-do-i-merge-two-dictionaries-in-a-single-expression-in-python
    -taking-union-o'.
    """
    result = {}
    for dictionary in dictionaries:
        result.update(dictionary)
    return result
             
             
def show(V, name=None, dec=3):
    """Pretty print matrix with rounded entries."""
    if name:
        print(name, '=')
    pprint(Matrix(np.round(V, dec)))
    

def play(anim):
    """Display matplotlib animation. For use in Jupyter notebook."""
    display(HTML(anim.to_jshtml()))


# Useful for accelerator physics
#------------------------------------------------------------------------------
def rotation_matrix(phi):
    return np.array([[np.cos(phi), np.sin(phi)], [-np.sin(phi), np.cos(phi)]])
    

def phase_adv_matrix(phi1, phi2):
    R = np.zeros((4, 4))
    R[:2, :2] = rotation_matrix(phi1)
    R[2:, 2:] = rotation_matrix(phi2)
    return R
    
    
def mat2vec(Sigma):
    """Return vector of independent elements in 4x4 symmetric matrix Sigma."""
    return Sigma[np.triu_indices(4)]
                     
                     
def vec2mat(vec):
    """Return 4x4 symmetric matrix from 10 element vector."""
    Sigma = np.zeros((4, 4))
    indices = np.triu_indices(4)
    for val, (i, j) in zip(vec, zip(*indices)):
        Sigma[i, j] = val
    return symmetrize(Sigma)
                     
                     
def symmetrize(M):
    """Return a symmetrized version of M.
    
    M : NumPy array
        A square upper or lower triangular matrix.
    """
    return M + M.T - np.diag(M.diagonal())
    
    
def rand_rows(X, n):
    """Return random subset of 2D array."""
    nrows = X.shape[0]
    if n >= nrows:
        return X
    idx = np.random.choice(X.shape[0], n, replace=False)
    return X[idx, :]
    
    
def cov2corr(cov_mat):
    """Return correlation matrix from covariance matrix."""
    D = np.sqrt(np.diag(cov_mat.diagonal()))
    Dinv = la.inv(D)
    corr_mat = la.multi_dot([Dinv, cov_mat, Dinv])
    return corr_mat


def Vmat_2D(alpha_x, beta_x, alpha_y, beta_y):
    """4D normalization matrix (uncoupled)"""
    def V_uu(alpha, beta):
        return np.array([[beta, 0.0], [-alpha, 1.0]]) / np.sqrt(beta)
    V = np.zeros((4, 4))
    V[:2, :2] = V_uu(alpha_x, beta_x)
    V[2:, 2:] = V_uu(alpha_y, beta_y)
    return V
    
    
def get_phase_adv(beta_x, beta_y, s, units='deg'):
    """Compute phase advance as function of s."""
    n_pts = len(s)
    phases = np.zeros((n_pts, 2))
    for i in range(n_pts):
        phases[i, 0] = trapz(1 / beta_x[:i], s[:i])
        phases[i, 1] = trapz(1 / beta_y[:i], s[:i]) # radians
    if units == 'deg':
        phases = np.degrees(phases)
    elif units == 'tune':
        phases /= 2*np.pi
    phases_df = pd.DataFrame(phases, columns=['x','y'])
    phases_df['s'] = s
    return phases_df
