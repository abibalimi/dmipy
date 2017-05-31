# -*- coding: utf-8 -*-
import numpy as np
from . import three_dimensional_models
from . import utils
from microstruktur.signal_models.spherical_convolution import sh_convolution
from dipy.reconst.shm import real_sym_sh_mrtrix
from scipy import stats
MicrostrukturModel = three_dimensional_models.MicrostrukturModel
WATSON_SH_ORDER = 14


class SD2I1BinghamDispersedStick(MicrostrukturModel):
    r""" The Bingham-Dispersed [1] Stick model [2] - a cylinder with zero
    radius - for intra-axonal diffusion. Allows for anisotropic dispersion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    psi : float,
        angle in radians of the bingham distribution around mu [0, pi].
    kappa : float,
        first concentration parameter of the Bingham distribution.
        defined as kappa = kappa1 - kappa3.
    beta : float,
        second concentration parameter of the Bingham distribution.
        defined as beta = kappa2 - kappa3. Bingham becomes Watson when beta=0.
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.

    References
    ----------
    .. [2] Behrens et al.
           "Characterization and propagation of uncertainty in
            diffusion-weighted MR imaging"
           Magnetic Resonance in Medicine (2003)
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, 3),
        'psi': (0, np.pi),
        'kappa': (0, 16),
        'beta': (0, 16)
    }

    def __init__(self, mu=None, lambda_par=None,
                 kappa=None, beta=None, psi=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.psi = psi
        self.kappa = kappa
        self.beta = beta

    def __call__(self, bvals, n, shell_indices=None, **kwargs):
        r'''
        Parameters
        ----------
        bvals : float or array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.

        Returns
        -------
        attenuation : float or array, shape(N),
            signal attenuation
        '''
        sh_order = WATSON_SH_ORDER
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        psi = kwargs.get('psi', self.psi)
        kappa = kwargs.get('kappa', self.kappa)
        beta = kwargs.get('beta', self.beta)
        if shell_indices is None:
            msg = "argument shell_indices is needed"
            raise ValueError(msg)

        bingham = three_dimensional_models.SD2Bingham(mu=mu, psi=psi,
                                                      kappa=kappa, beta=beta)
        sh_bingham = bingham.spherical_harmonics_representation()
        stick = three_dimensional_models.I1Stick(mu=mu, lambda_par=lambda_par)

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = stick.rotational_harmonics_representation(
                bval=bval_mean)
            # convolving micro-environment with bingham distribution
            E_dispersed_sh = sh_convolution(sh_bingham, rh_stick, sh_order)
            # recover signal values from bingham-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD2I2BinghamDispersedSodermanCylinder(MicrostrukturModel):
    r""" The Bingham-Dispersed [1] Soderman cylinder model [2] - assuming
    limits of pulse separation towards infinity and pulse duration towards zero
    - for intra-axonal diffusion. Allows for anisotropic dispersion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    psi : float,
        angle in radians of the bingham distribution around mu [0, pi].
    kappa : float,
        first concentration parameter of the Bingham distribution.
        defined as kappa = kappa1 - kappa3.
    beta : float,
        second concentration parameter of the Bingham distribution.
        defined as beta = kappa2 - kappa3. Bingham becomes Watson when beta=0.
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    diameter : float,
        cylinder (axon) diameter in meters.

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [2] Söderman, Olle, and Bengt Jönsson. "Restricted diffusion in
        cylindrical geometry." Journal of Magnetic Resonance, Series A
        117.1 (1995): 94-97.
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, 3),
        'diameter': (1e-10, 50e-6),
        'psi': (0, np.pi),
        'kappa': (0, 16),
        'beta': (0, 16)
    }

    def __init__(self, mu=None, lambda_par=None, diameter=None,
                 kappa=None, beta=None, psi=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.diameter = diameter
        self.psi = psi
        self.kappa = kappa
        self.beta = beta

    def __call__(self, bvals, n, delta=None, Delta=None, shell_indices=None,
                 **kwargs):
        r"""
        Parameters
        ----------
        bvals : array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        delta : array, shape(N),
            pulse duration in seconds.
        Delta : array, shape(N),
            pulse separation in seconds
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        E : array, shape(N),
            signal attenuation.
        """
        sh_order = WATSON_SH_ORDER
        if (
            delta is None or Delta is None
        ):
            raise ValueError('This class needs non-None delta and Delta')
        if shell_indices is None:
            msg = "This class needs non-None shell_indices"
            raise ValueError(msg)
        diameter = kwargs.get('diameter', self.diameter)
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        psi = kwargs.get('psi', self.psi)
        kappa = kwargs.get('kappa', self.kappa)
        beta = kwargs.get('beta', self.beta)

        bingham = three_dimensional_models.SD2Bingham(mu=mu, psi=psi,
                                                      kappa=kappa, beta=beta)
        sh_bingham = bingham.spherical_harmonics_representation()
        soderman = three_dimensional_models.I2CylinderSodermanApproximation(
            mu=mu, lambda_par=lambda_par, diameter=diameter
        )

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            delta_mean = delta[bval_mask].mean()
            Delta_mean = Delta[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = soderman.rotational_harmonics_representation(
                bval=bval_mean, delta=delta_mean, Delta=Delta_mean)
            # convolving micro-environment with bingham distribution
            E_dispersed_sh = sh_convolution(sh_bingham, rh_stick, sh_order)
            # recover signal values from bingham-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD2I3BinghamDispersedCallaghanCylinder(MicrostrukturModel):
    r""" The Bingham-Dispersed [1] Callaghan cylinder model [2] - assuming
    finite pulse separation and limit of pulse duration towards zero - for
    intra-axonal diffusion. Allows for anisotropic dispersion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    psi : float,
        angle in radians of the bingham distribution around mu [0, pi].
    kappa : float,
        first concentration parameter of the Bingham distribution.
        defined as kappa = kappa1 - kappa3.
    beta : float,
        second concentration parameter of the Bingham distribution.
        defined as beta = kappa2 - kappa3. Bingham becomes Watson when beta=0.
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    diameter : float,
        cylinder (axon) diameter in meters.

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [2] Callaghan, Paul T. "Pulsed-gradient spin-echo NMR for planar,
        cylindrical, and spherical pores under conditions of wall
        relaxation." Journal of magnetic resonance, Series A 113.1 (1995):
        53-59.
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, 3),
        'diameter': (1e-10, 50e-6),
        'psi': (0, np.pi),
        'kappa': (0, 16),
        'beta': (0, 16)
    }

    def __init__(self, mu=None, lambda_par=None, diameter=None,
                 kappa=None, beta=None, psi=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.diameter = diameter
        self.psi = psi
        self.kappa = kappa
        self.beta = beta

    def __call__(self, bvals, n, delta=None, Delta=None, shell_indices=None,
                 **kwargs):
        r"""
        Parameters
        ----------
        bvals : array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        delta : array, shape(N),
            pulse duration in seconds.
        Delta : array, shape(N),
            pulse separation in seconds
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        E : array, shape(N),
            signal attenuation.
        """
        sh_order = WATSON_SH_ORDER
        if (
            delta is None or Delta is None
        ):
            raise ValueError('This class needs non-None delta and Delta')
        if shell_indices is None:
            msg = "This class needs non-None shell_indices"
            raise ValueError(msg)
        diameter = kwargs.get('diameter', self.diameter)
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        psi = kwargs.get('psi', self.psi)
        kappa = kwargs.get('kappa', self.kappa)
        beta = kwargs.get('beta', self.beta)

        bingham = three_dimensional_models.SD2Bingham(mu=mu, psi=psi,
                                                      kappa=kappa, beta=beta)
        sh_bingham = bingham.spherical_harmonics_representation()
        callaghan = three_dimensional_models.I3CylinderCallaghanApproximation(
            mu=mu, lambda_par=lambda_par, diameter=diameter
        )

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            delta_mean = delta[bval_mask].mean()
            Delta_mean = Delta[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = callaghan.rotational_harmonics_representation(
                bval=bval_mean, delta=delta_mean, Delta=Delta_mean)
            # convolving micro-environment with bingham distribution
            E_dispersed_sh = sh_convolution(sh_bingham, rh_stick, sh_order)
            # recover signal values from bingham-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD2I4BinghamDispersedGaussianPhaseCylinder(MicrostrukturModel):
    r""" The Bingham-Dispersed [1] van gelderen cylinder model [2] - assuming
    finite pulse separation and pulse duration - for intra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    psi : float,
        angle in radians of the bingham distribution around mu [0, pi].
    kappa : float,
        first concentration parameter of the Bingham distribution.
        defined as kappa = kappa1 - kappa3.
    beta : float,
        second concentration parameter of the Bingham distribution.
        defined as beta = kappa2 - kappa3. Bingham becomes Watson when beta=0.
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    diameter : float,
        cylinder (axon) diameter in meters.

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [1] Van Gelderen et al.
        "Evaluation of Restricted Diffusion
        in Cylinders. Phosphocreatine in Rabbit Leg Muscle"
        Journal of Magnetic Resonance Series B (1994)
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, 3),
        'diameter': (1e-10, 50e-6),
        'psi': (0, np.pi),
        'kappa': (0, 16),
        'beta': (0, 16)
    }

    def __init__(self, mu=None, lambda_par=None, diameter=None,
                 kappa=None, beta=None, psi=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.diameter = diameter
        self.psi = psi
        self.kappa = kappa
        self.beta = beta

    def __call__(self, bvals, n, delta=None, Delta=None, shell_indices=None,
                 **kwargs):
        r"""
        Parameters
        ----------
        bvals : array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        delta : array, shape(N),
            pulse duration in seconds.
        Delta : array, shape(N),
            pulse separation in seconds
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        E : array, shape(N),
            signal attenuation.
        """
        sh_order = WATSON_SH_ORDER
        if (
            delta is None or Delta is None
        ):
            raise ValueError('This class needs non-None delta and Delta')
        if shell_indices is None:
            msg = "This class needs non-None shell_indices"
            raise ValueError(msg)
        diameter = kwargs.get('diameter', self.diameter)
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        psi = kwargs.get('psi', self.psi)
        kappa = kwargs.get('kappa', self.kappa)
        beta = kwargs.get('beta', self.beta)

        bingham = three_dimensional_models.SD2Bingham(mu=mu, psi=psi,
                                                      kappa=kappa, beta=beta)
        sh_bingham = bingham.spherical_harmonics_representation()
        vg = three_dimensional_models.I4CylinderGaussianPhaseApproximation(
            mu=mu, lambda_par=lambda_par, diameter=diameter
        )

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            delta_mean = delta[bval_mask].mean()
            Delta_mean = Delta[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = vg.rotational_harmonics_representation(
                bval=bval_mean, delta=delta_mean, Delta=Delta_mean)
            # convolving micro-environment with bingham distribution
            E_dispersed_sh = sh_convolution(sh_bingham, rh_stick, sh_order)
            # recover signal values from bingham-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD3I1WatsonDispersedStick(MicrostrukturModel):
    r""" The Watson-Dispersed [1] Stick model [2] - a cylinder with zero radius
    - for intra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [2] Behrens et al.
           "Characterization and propagation of uncertainty in
            diffusion-weighted MR imaging"
           Magnetic Resonance in Medicine (2003)
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, np.inf),
        'kappa': (0, 16)
    }

    def __init__(self, mu=None, lambda_par=None, kappa=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.kappa = kappa

    def __call__(self, bvals, n, **kwargs):
        r'''
        Parameters
        ----------
        bvals : float or array, shape(N),
            b-values in s/mm^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.

        Returns
        -------
        attenuation : float or array, shape(N),
            signal attenuation
        '''
        sh_order = WATSON_SH_ORDER
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        kappa = kwargs.get('kappa', self.kappa)
        shell_indices = kwargs.get('shell_indices')
        if shell_indices is None:
            msg = "argument shell_indices is needed"
            raise ValueError(msg)

        watson = three_dimensional_models.SD3Watson(mu=mu, kappa=kappa)
        sh_watson = watson.spherical_harmonics_representation()
        stick = three_dimensional_models.I1Stick(mu=mu, lambda_par=lambda_par)

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = stick.rotational_harmonics_representation(
                bval=bval_mean)
            # convolving micro-environment with watson distribution
            E_dispersed_sh = sh_convolution(sh_watson, rh_stick, sh_order)
            # recover signal values from watson-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD3I2WatsonDispersedSodermanCylinder(MicrostrukturModel):
    r""" The Watson-Dispersed [1] Soderman cylinder model [2] - assuming limits
    of pulse separation towards infinity and pulse duration towards zero - for
    intra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi]..
    lambda_par : float,
        parallel diffusivity in 10^9m^2/s.
    kappa : float,
        concentration parameter of Watson distribution.
    diameter : float,
        cylinder (axon) diameter in meters.

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [2] Söderman, Olle, and Bengt Jönsson. "Restricted diffusion in
        cylindrical geometry." Journal of Magnetic Resonance, Series A
        117.1 (1995): 94-97.
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, np.inf),
        'kappa': (0, 16),
        'diameter': (1e-10, 50e-6),
    }

    def __init__(self, mu=None, lambda_par=None, kappa=None, diameter=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.kappa = kappa
        self.diameter = diameter

    def __call__(self, bvals, n, delta=None, Delta=None, shell_indices=None,
                 **kwargs):
        r"""
        Parameters
        ----------
        bvals : array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        delta : array, shape(N),
            pulse duration in seconds.
        Delta : array, shape(N),
            pulse separation in seconds
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        E : array, shape(N),
            signal attenuation.
        """
        sh_order = WATSON_SH_ORDER
        if (
            delta is None or Delta is None
        ):
            raise ValueError('This class needs non-None delta and Delta')
        if shell_indices is None:
            msg = "This class needs non-None shell_indices"
            raise ValueError(msg)
        diameter = kwargs.get('diameter', self.diameter)
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        kappa = kwargs.get('kappa', self.kappa)

        watson = three_dimensional_models.SD3Watson(mu=mu, kappa=kappa)
        sh_watson = watson.spherical_harmonics_representation(
            sh_order=sh_order
        )
        soderman = three_dimensional_models.I2CylinderSodermanApproximation(
            mu=mu, lambda_par=lambda_par, diameter=diameter
        )

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            delta_mean = delta[bval_mask].mean()
            Delta_mean = Delta[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = soderman.rotational_harmonics_representation(
                bval=bval_mean, delta=delta_mean, Delta=Delta_mean)
            # convolving micro-environment with watson distribution
            E_dispersed_sh = sh_convolution(sh_watson, rh_stick, sh_order)
            # recover signal values from watson-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD3I3WatsonDispersedCallaghanCylinder(MicrostrukturModel):
    r""" The Watson-Dispersed [1] Calalghan cylinder model [2] - assuming
    finite pulse separation and the limit of pulse duration towards zero - for
    intra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    kappa : float,
        concentration parameter of Watson distribution.
    diameter : float,
        cylinder (axon) diameter in meters.

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [2] Callaghan, Paul T. "Pulsed-gradient spin-echo NMR for planar,
        cylindrical, and spherical pores under conditions of wall
        relaxation." Journal of magnetic resonance, Series A 113.1 (1995):
        53-59.
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, np.inf),
        'kappa': (0, 16),
        'diameter': (1e-10, 50e-6),
    }

    def __init__(self, mu=None, lambda_par=None, kappa=None, diameter=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.kappa = kappa
        self.diameter = diameter

    def __call__(self, bvals, n, delta=None, Delta=None, shell_indices=None,
                 **kwargs):
        r"""
        Parameters
        ----------
        bvals : array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        delta : array, shape(N),
            pulse duration in seconds.
        Delta : array, shape(N),
            pulse separation in seconds
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        E : array, shape(N),
            signal attenuation.
        """
        sh_order = WATSON_SH_ORDER
        if (
            delta is None or Delta is None
        ):
            raise ValueError('This class needs non-None delta and Delta')
        if shell_indices is None:
            msg = "This class needs non-None shell_indices"
            raise ValueError(msg)
        diameter = kwargs.get('diameter', self.diameter)
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        kappa = kwargs.get('kappa', self.kappa)

        watson = three_dimensional_models.SD3Watson(mu=mu, kappa=kappa)
        sh_watson = watson.spherical_harmonics_representation(
            sh_order=sh_order
        )
        callaghan = three_dimensional_models.I3CylinderCallaghanApproximation(
            mu=mu, lambda_par=lambda_par, diameter=diameter
        )

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            delta_mean = delta[bval_mask].mean()
            Delta_mean = Delta[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = callaghan.rotational_harmonics_representation(
                bval=bval_mean, delta=delta_mean, Delta=Delta_mean)
            # convolving micro-environment with watson distribution
            E_dispersed_sh = sh_convolution(sh_watson, rh_stick, sh_order)
            # recover signal values from watson-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD3I4WatsonDispersedGaussianPhaseCylinder(MicrostrukturModel):
    r""" The Watson-Dispersed [1] Van Gelderen cylinder model [2] - assuming
    finite pulse separation and pulse duration - for intra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    kappa : float,
        concentration parameter of Watson distribution.
    diameter : float,
        cylinder (axon) diameter in meters.

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [1] Van Gelderen et al.
        "Evaluation of Restricted Diffusion
        in Cylinders. Phosphocreatine in Rabbit Leg Muscle"
        Journal of Magnetic Resonance Series B (1994)
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, np.inf),
        'kappa': (0, 16),
        'diameter': (1e-10, 50e-6),
    }

    def __init__(self, mu=None, lambda_par=None, kappa=None, diameter=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.kappa = kappa
        self.diameter = diameter

    def __call__(self, bvals, n, delta=None, Delta=None, shell_indices=None,
                 **kwargs):
        r"""
        Parameters
        ----------
        bvals : array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        delta : array, shape(N),
            pulse duration in seconds.
        Delta : array, shape(N),
            pulse separation in seconds
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        E : array, shape(N),
            signal attenuation
        """
        sh_order = WATSON_SH_ORDER
        if (
            delta is None or Delta is None
        ):
            raise ValueError('This class needs non-None delta and Delta')
        if shell_indices is None:
            msg = "This class needs non-None shell_indices"
            raise ValueError(msg)
        diameter = kwargs.get('diameter', self.diameter)
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        kappa = kwargs.get('kappa', self.kappa)

        watson = three_dimensional_models.SD3Watson(mu=mu, kappa=kappa)
        sh_watson = watson.spherical_harmonics_representation(
            sh_order=sh_order
        )
        vg = three_dimensional_models.I4CylinderGaussianPhaseApproximation(
            mu=mu, lambda_par=lambda_par, diameter=diameter
        )

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            delta_mean = delta[bval_mask].mean()
            Delta_mean = Delta[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of stick
            rh_stick = vg.rotational_harmonics_representation(
                bval=bval_mean, delta=delta_mean, Delta=Delta_mean)
            # convolving micro-environment with watson distribution
            E_dispersed_sh = sh_convolution(sh_watson, rh_stick, sh_order)
            # recover signal values from watson-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD2E4BinghamDispersedZeppelin(MicrostrukturModel):
    r""" The Bingham-Dispersed [1] Zeppelin model [2] - for typically
    extra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    lambda_perp : float,
        perpendicular diffusivity in 10^9 m^2/s.
    psi : float,
        angle in radians of the bingham distribution around mu [0, pi].
    kappa : float,
        first concentration parameter of the Bingham distribution.
        defined as kappa = kappa1 - kappa3.
    beta : float,
        second concentration parameter of the Bingham distribution.
        defined as beta = kappa2 - kappa3. Bingham becomes Watson when beta=0.

    References
    ----------
    .. [1] Panagiotaki et al.
           "Compartment models of the diffusion MR signal in brain white
            matter: a taxonomy and comparison". NeuroImage (2012)
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, 3),
        'lambda_perp': (0, 3),
        'psi': (0, np.pi),
        'kappa': (0, 16),
        'beta': (0, 16)
    }

    def __init__(self, mu=None, lambda_par=None, lambda_perp=None,
                 kappa=None, beta=None, psi=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.lambda_perp = lambda_perp
        self.psi = psi
        self.kappa = kappa
        self.beta = beta

    def __call__(self, bvals, n, shell_indices=None, **kwargs):
        r'''
        Parameters
        ----------
        bvals : float or array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        attenuation : float or array, shape(N),
            signal attenuation
        '''
        sh_order = WATSON_SH_ORDER
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        lambda_perp = kwargs.get('lambda_perp', self.lambda_perp)
        mu = kwargs.get('mu', self.mu)
        kappa = kwargs.get('kappa', self.kappa)
        beta = kwargs.get('beta', self.beta)
        psi = kwargs.get('psi', self.psi)
        if shell_indices is None:
            msg = "argument shell_indices is needed"
            raise ValueError(msg)

        bingham = three_dimensional_models.SD2Bingham(mu=mu, kappa=kappa,
                                                      beta=beta, psi=psi)
        sh_bingham = bingham.spherical_harmonics_representation()
        zeppelin = three_dimensional_models.E4Zeppelin(
            mu=mu, lambda_par=lambda_par, lambda_perp=lambda_perp
        )

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of zeppelin
            rh_zeppelin = zeppelin.rotational_harmonics_representation(
                bval=bval_mean
            )
            # convolving micro-environment with bingham distribution
            E_dispersed_sh = sh_convolution(sh_bingham, rh_zeppelin, sh_order)
            # recover signal values from bingham-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class SD3E4WatsonDispersedZeppelin(MicrostrukturModel):
    r""" The Watson-Dispersed Zeppelin model [1] - a cylinder with zero radius-
    for intra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    kappa : float,
        concentration parameter of Watson distribution.
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    lambda_perp : float,
        perpendicular diffusivity in 10^9 m^2/s.

    References
    ----------
    .. [1] Panagiotaki et al.
           "Compartment models of the diffusion MR signal in brain white
            matter: a taxonomy and comparison". NeuroImage (2012)
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, np.inf),
        'lambda_perp': (0, np.inf),
        'kappa': (0, 16)
    }

    def __init__(self, mu=None, lambda_par=None, lambda_perp=None, kappa=None):
        self.mu = mu
        self.lambda_par = lambda_par
        self.lambda_perp = lambda_perp
        self.kappa = kappa

    def __call__(self, bvals, n, shell_indices=None, **kwargs):
        r'''
        Parameters
        ----------
        bvals : float or array, shape(N),
            b-values in s/mm^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        shell_indices : array, shape(N),
            array with integers reflecting to which acquisition shell a
            measurement belongs. zero for b0 measurements, 1 for the first
            shell, 2 for the second, etc.

        Returns
        -------
        E : float or array, shape(N),
            signal attenuation
        '''
        sh_order = WATSON_SH_ORDER
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        lambda_perp = kwargs.get('lambda_perp', self.lambda_perp)
        mu = kwargs.get('mu', self.mu)
        kappa = kwargs.get('kappa', self.kappa)
        if shell_indices is None:
            msg = "argument shell_indices is needed"
            raise ValueError(msg)

        watson = three_dimensional_models.SD3Watson(mu=mu, kappa=kappa)
        sh_watson = watson.spherical_harmonics_representation()
        zeppelin = three_dimensional_models.E4Zeppelin(mu=mu,
                                                       lambda_par=lambda_par,
                                                       lambda_perp=lambda_perp)

        E = np.ones_like(bvals)
        for shell_index in np.arange(1, shell_indices.max() + 1):  # per shell
            bval_mask = shell_indices == shell_index
            bvecs_shell = n[bval_mask]  # what bvecs in that shell
            bval_mean = bvals[bval_mask].mean()
            _, theta_, phi_ = utils.cart2sphere(bvecs_shell).T
            sh_mat = real_sym_sh_mrtrix(sh_order, theta_, phi_)[0]

            # rotational harmonics of zeppelin
            rh_zeppelin = zeppelin.rotational_harmonics_representation(
                bval=bval_mean
            )
            # convolving micro-environment with watson distribution
            E_dispersed_sh = sh_convolution(sh_watson, rh_zeppelin, sh_order)
            # recover signal values from watson-convolved spherical harmonics
            E[bval_mask] = np.dot(sh_mat, E_dispersed_sh)
        return E


class DD1I4GammaDistributedGaussianPhaseCylinder(MicrostrukturModel):
    r""" The Watson-Dispersed [1] Van Gelderen cylinder model [2] - assuming
    finite pulse separation and pulse duration - for intra-axonal diffusion.

    Parameters
    ----------
    mu : array, shape(2),
        angles [theta, phi] representing main orientation on the sphere.
        theta is inclination of polar angle of main angle mu [0, pi].
        phi is polar angle of main angle mu [-pi, pi].
    lambda_par : float,
        parallel diffusivity in 10^9 m^2/s.
    alpha : float,
        shape of the gamma distribution.
    beta : float,
        scale of the gamma distrubution. Different from Bingham distribution!

    References
    ----------
    .. [1] Kaden et al.
        "Parametric spherical deconvolution: inferring anatomical
        connectivity using diffusion MR imaging". NeuroImage (2007)
    .. [1] Van Gelderen et al.
        "Evaluation of Restricted Diffusion
        in Cylinders. Phosphocreatine in Rabbit Leg Muscle"
        Journal of Magnetic Resonance Series B (1994)
    """

    _parameter_ranges = {
        'mu': ([0, -np.pi], [np.pi, np.pi]),
        'lambda_par': (0, np.inf),
        'alpha': (1e-10, np.inf),
        'beta': (1e-10, np.inf),
    }

    def __init__(self, mu=None, lambda_par=None, alpha=None, beta=None,
                 radius_integral_steps=35):
        self.mu = mu
        self.lambda_par = lambda_par
        self.alpha = alpha
        self.beta = beta
        self.radius_integral_steps = radius_integral_steps

    def __call__(self, bvals, n, delta=None, Delta=None, **kwargs):
        r"""
        Parameters
        ----------
        bvals : array, shape(N),
            b-values in s/m^2.
        n : array, shape(N x 3),
            b-vectors in cartesian coordinates.
        delta : array, shape(N),
            pulse duration in seconds.
        Delta : array, shape(N),
            pulse separation in seconds

        Returns
        -------
        E : array, shape(N),
            signal attenuation
        """
        if (
            delta is None or Delta is None
        ):
            raise ValueError('This class needs non-None delta and Delta')
        lambda_par = kwargs.get('lambda_par', self.lambda_par)
        mu = kwargs.get('mu', self.mu)
        alpha = kwargs.get('alpha', self.alpha)
        beta = kwargs.get('beta', self.beta)

        gamma_dist = stats.gamma(alpha, scale=beta)
        radius_max = gamma_dist.mean() + 6 * gamma_dist.std()
        radii = np.linspace(1e-50, radius_max, self.radius_integral_steps)
        area = np.pi * radii ** 2
        radii_pdf = gamma_dist.pdf(radii)
        radii_pdf_area = radii_pdf * area
        radii_pdf_normalized = (
            radii_pdf_area /
            np.trapz(x=radii, y=radii_pdf_area)
        )

        vg = three_dimensional_models.I4CylinderGaussianPhaseApproximation(
            mu=mu, lambda_par=lambda_par
        )
        
        E = np.empty(
            (self.radius_integral_steps, len(bvals)),
            dtype=float
        )
        for i, radius in enumerate(radii):
            E[i] = (
                radii_pdf_normalized[i] *
                vg(bvals, n=n, delta=delta, Delta=Delta, diameter=radius * 2)
            )

        E = np.trapz(E, x=radii, axis=0)
        return E
