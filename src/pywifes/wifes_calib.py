from __future__ import print_function
from astropy.io import fits as pyfits
from math import factorial
import matplotlib.pyplot as plt
import numpy
import os
import pickle
import scipy.interpolate

from .logger_config import custom_print
import logging

from . import wifes_ephemeris
from .pywifes import imcopy
from .wifes_metadata import metadata_dir, __version__
from .wifes_utils import arguments, is_halfframe, is_taros

# Redirect print statements to logger
logger = logging.getLogger("PyWiFeS")
print = custom_print(logger)

# ------------------------------------------------------------------------
# reference star information!
stdstar_fn = os.path.join(metadata_dir, "stdstar_lookup_table.dat")
f1 = open(stdstar_fn, "r")
stdstar_lines = f1.readlines()[1:]
f1.close()

ref_fname_lookup = {}
ref_coords_lookup = {}
ref_flux_lookup = {}
ref_telluric_lookup = {}
for line in stdstar_lines:
    lns = line.split()
    fn = lns[0]
    name = lns[1]
    radec = "%s %s" % (lns[2], lns[3])
    is_flux_standard = bool(int(lns[5]))  # Skip a line for the comments
    is_telluric_standard = bool(int(lns[6]))
    ref_fname_lookup[name] = fn
    ref_coords_lookup[name] = radec
    ref_flux_lookup[name] = is_flux_standard
    ref_telluric_lookup[name] = is_telluric_standard

# extinction interpolation object
extinct_fn = os.path.join(metadata_dir, "sso_extinction.dat")
extinct_data = numpy.loadtxt(extinct_fn)
sso_extinct_interp = scipy.interpolate.interp1d(
    extinct_data[:, 0], extinct_data[:, 1], bounds_error=False, fill_value=numpy.nan
)

# ------------------------------------------------------------------------
# high-level function to find nearest standard star for a given frame!
stdstar_list = list(ref_coords_lookup.keys())
stdstar_list.sort()
nstds = len(stdstar_list)
stdstar_ra_array = numpy.zeros(nstds, dtype="d")
stdstar_dec_array = numpy.zeros(nstds, dtype="d")
for i in range(nstds):
    stdstar_radec = ref_coords_lookup[stdstar_list[i]]
    stdstar_ra, stdstar_dec = wifes_ephemeris.sex2dd(stdstar_radec)
    stdstar_ra_array[i] = stdstar_ra
    stdstar_dec_array[i] = stdstar_dec


def find_nearest_stdstar(inimg, data_hdu=0):
    f = pyfits.open(inimg)
    radec = "%s %s" % (f[data_hdu].header["RA"], f[data_hdu].header["DEC"])
    f.close()
    ra, dec = wifes_ephemeris.sex2dd(radec)
    angsep_array = (
        3600.0
        * (
            (dec - stdstar_dec_array) ** 2
            + (numpy.cos(numpy.radians(dec)) * (ra - stdstar_ra_array)) ** 2
        )
        ** 0.5
    )
    best_ind = numpy.argmin(angsep_array)
    return stdstar_list[best_ind], angsep_array[best_ind]


# ------------------------------------------------------------------------
# scripts for masking out certain wavelength regions
def wavelength_mask(wave_array, band_list):
    mask = numpy.ones(len(wave_array))
    for band in band_list:
        mask *= (wave_array <= band[0]) + (wave_array >= band[1])
    return mask


# O2  bands are saturated - don't depend on airmass
# H2O bands DO depend on airmass!!
O2_telluric_bands = [[6856.0, 6956.0], [7584.0, 7693.0]]
# [7547.0, 7693.0]]

H2O_telluric_bands = [
    [6270.0, 6290.0],
    [7154.0, 7332.0],
    [8114.0, 8344.0],
    [8937.0, 9194.0],
    [9270.0, 9776.0],
]

strong_H2O_telluric_bands = [
    [6270.0, 6290.0],
    [7154.0, 7332.0],
    [8114.0, 8344.0],
    [8937.0, 9194.0],
    [9270.0, 9400.0],
]

master_H2O_telluric_bands = [
    [5870.0, 6000.0],
    [6270.0, 6290.0],
    [6459.0, 6598.0],
    [7154.0, 7332.0],
    [8114.0, 8344.0],
    [8937.0, 9194.0],
    [9270.0, 9776.0],
]


# functions for masking telluric and halpha features
def strong_telluric_mask(wave_array):
    return wavelength_mask(wave_array, O2_telluric_bands + strong_H2O_telluric_bands)


def telluric_mask(wave_array):
    return wavelength_mask(wave_array, O2_telluric_bands + H2O_telluric_bands)


def halpha_mask(wave_array):
    ha_bands = [[6550.0, 6575.0]]
    return wavelength_mask(wave_array, ha_bands)


# ------------------------------------------------------------------------
def load_wifes_cube(cube_fn, ytrim=[0, 0], return_dq=False):
    f = pyfits.open(cube_fn)

    # get wavelength array
    if is_halfframe(cube_fn):
        if is_taros(cube_fn):
            nx = 12
        else:
            nx = 13
    else:
        nx = 25
    ny, nlam = numpy.shape(f[1].data)
    lam0 = f[1].header["CRVAL1"]
    dlam = f[1].header["CDELT1"]
    lam_array = lam0 + dlam * numpy.arange(nlam, dtype="d")
    # get data and variance
    obj_cube_data = numpy.zeros([nlam, ny - sum(ytrim), nx], dtype="d")
    obj_cube_var = numpy.zeros([nlam, ny - sum(ytrim), nx], dtype="d")
    if return_dq:
        obj_cube_dq = numpy.zeros([nlam, ny - sum(ytrim), nx], dtype="d")

    for i in range(nx):
        curr_hdu = i + 1
        curr_data = f[curr_hdu].data[ytrim[0]:ny - ytrim[1], :]
        curr_var = f[curr_hdu + nx].data[ytrim[0]:ny - ytrim[1], :]

        obj_cube_data[:, :, i] = curr_data.T
        obj_cube_var[:, :, i] = curr_var.T

        if return_dq:
            curr_dq = f[curr_hdu + 2 * nx].data[ytrim[0]:ny - ytrim[1], :]
            obj_cube_dq[:, :, i] = curr_dq.T
    f.close()
    if return_dq:
        # return flux, variance, wavelength, dq
        return obj_cube_data, obj_cube_var, lam_array, obj_cube_dq
    else:
        # return flux, variance, wavelength
        return obj_cube_data, obj_cube_var, lam_array


# ------------------------------------------------------------------------
def extract_wifes_stdstar(
    cube_fn,
    x_ctr=None,
    y_ctr=None,
    extract_radius=5.0,
    sky_radius=8.0,
    xtrim=4,
    ytrim=8,
    wmask=500,  # mask wavelength extremes when peak-finding
    save_mode=None,
    save_fn=None,
    debug=False,
    interactive_plot=False,
):
    if debug:
        print(arguments())

    slice_size_arcsec = 1.0
    if is_halfframe(cube_fn) and not is_taros(cube_fn):
        first = 7
    else:
        first = 1

    # check spatial binning!
    f = pyfits.open(cube_fn)
    exptime = float(f[1].header["EXPTIME"])
    bin_w, bin_y = [int(b) for b in f[1].header["CCDSUM"].split()]
    wmask = wmask // bin_w
    ytrim = ytrim // bin_y
    pix_size_arcsec = bin_y * 0.5

    # load the cube data
    init_obj_cube_data, init_obj_cube_var, lam_array, init_obj_cube_dq = load_wifes_cube(cube_fn, return_dq=True)

    inlam, iny, inx = numpy.shape(init_obj_cube_data)
    obj_cube_data = init_obj_cube_data[:, ytrim:iny - ytrim, xtrim:inx - xtrim]
    obj_cube_var = init_obj_cube_var[:, ytrim:iny - ytrim, xtrim:inx - xtrim]
    obj_cube_dq = init_obj_cube_dq[:, ytrim:iny - ytrim, xtrim:inx - xtrim]
    nlam, ny, nx = numpy.shape(obj_cube_data)
    obj_cube_data[numpy.logical_or(numpy.isnan(obj_cube_dq), obj_cube_dq > 0)] = numpy.nan

    # get stdstar centroid
    lin_x = numpy.arange(nx, dtype="d")
    lin_y = numpy.arange(ny, dtype="d")
    full_x, full_y = numpy.meshgrid(lin_x, lin_y)

    if x_ctr is None or y_ctr is None:
        cube_im = numpy.nansum(obj_cube_data[wmask:nlam - wmask, :, :], axis=0)
        maxind = numpy.nonzero(
            cube_im == cube_im.max()
        )  # numpy.nonzero returns indices of nonzero elements
        y_ctr = maxind[0][0]
        x_ctr = maxind[1][0]
    print(f"Extracting STD from IFU (x,y) = ({x_ctr + first + xtrim}, {y_ctr + 1 + ytrim})")

    # get *distance* of each pixels from stdstar center x/y
    pix_dists = (
        (slice_size_arcsec * (full_x - x_ctr)) ** 2
        + (pix_size_arcsec * (full_y - y_ctr)) ** 2
    ) ** 0.5
    sky_pix = numpy.nonzero((pix_dists >= sky_radius))
    obj_pix = numpy.nonzero((pix_dists <= extract_radius))

    sky_flux = numpy.nanmedian(obj_cube_data[:, sky_pix[0], sky_pix[1]], axis=1)
    std_flux = numpy.sum(obj_cube_data[:, obj_pix[0], obj_pix[1]], axis=1) - sky_flux * len(obj_pix[0])
    std_var = numpy.sum(obj_cube_var[:, obj_pix[0], obj_pix[1]], axis=1)

    # Enforce a S/N > 10 limit
    std_flux[std_flux / numpy.sqrt(std_var) < 10] = numpy.nan
    if interactive_plot:
        plt.plot(lam_array, sky_flux, label='sky_flux')
        plt.plot(lam_array, std_flux, label='std_flux')
        plt.plot(lam_array, std_var, label='std_var')
        plt.plot(lam_array, std_flux / numpy.sqrt(std_var), label='S/N')
        plt.legend()
        plt.yscale('log')
        plt.title(os.path.basename(cube_fn))
        plt.show()
        plt.close()

    # DIVIDE FLUX BY EXPTIME AND BIN SIZE!!!
    dlam = lam_array[1] - lam_array[0]
    fscale = exptime * dlam
    std_flux /= fscale
    std_var /= fscale**2
    sky_flux /= fscale

    # Filtering nan values in case of missing flux values, see #27
    filter_nan = ~numpy.isnan(std_flux)
    filtered_lam_array = lam_array[filter_nan]
    filtered_std_flux = std_flux[filter_nan]
    filtered_std_var = std_var[filter_nan]

    len_filtered_lam = len(filtered_lam_array)

    # return flux or save!
    if save_mode is None:
        f.close()
        return filtered_lam_array, filtered_std_flux
    elif save_mode == "ascii":
        f.close()
        save_data = numpy.zeros([len_filtered_lam, 3], dtype="d")
        save_data[:, 0] = filtered_lam_array
        save_data[:, 1] = filtered_std_flux
        save_data[:, 2] = filtered_std_var
        numpy.savetxt(save_fn, save_data)
    elif save_mode == "iraf":
        out_header = f[1].header
        out_header.set("CD1_1", f[1].header["CDELT1"])
        out_header.set("CD2_2", 1)
        out_header.set("CD3_3", 1)
        out_header.set("LTM3_3", 1)
        out_data = numpy.zeros([4, 1, len_filtered_lam], dtype="d")
        out_data[0, 0, :] = filtered_std_flux
        out_data[1, 0, :] = sky_flux
        out_data[2, 0, :] = filtered_std_var
        out_data[3, 0, :] = filtered_std_var
        out_hdu = pyfits.PrimaryHDU(data=out_data, header=out_header)
        outfits = pyfits.HDUList([out_hdu])
        outfits[0].header.set("PYWIFES", __version__, "PyWiFeS version")
        outfits.writeto(save_fn, overwrite=True)
        f.close()
    else:
        f.close()
        raise ValueError("Standard Star save format not recognized")


# ------------------------------------------------------------------------
# simple function to divide a cube by some spectrum
def wifes_cube_divide(inimg, outimg, corr_wave, corr_flux):
    corr_interp = scipy.interpolate.interp1d(
        corr_wave, corr_flux, bounds_error=False, fill_value=numpy.inf
    )  # set divided flux outside bounds to zero
    halfframe = is_halfframe(inimg)
    if halfframe:
        if is_taros(inimg):
            nslits = 12
        else:
            nslits = 13
    else:
        nslits = 25
    f3 = pyfits.open(inimg)
    # get the wavelength array
    wave0 = f3[1].header["CRVAL1"]
    dwave = f3[1].header["CDELT1"]
    nlam = numpy.shape(f3[1].data)[1]
    wave_array = wave0 + dwave * numpy.arange(nlam, dtype="d")
    # calculate the flux calibration array
    fcal_array = corr_interp(wave_array)
    outfits = pyfits.HDUList(f3)
    for i in range(nslits):
        curr_hdu = i + 1
        curr_flux = f3[curr_hdu].data
        curr_var = f3[curr_hdu + nslits].data
        out_flux = curr_flux / fcal_array
        out_var = curr_var / (fcal_array**2)
        # save to data cube
        outfits[curr_hdu].data = out_flux.astype("float32", casting="same_kind")
        outfits[curr_hdu].scale("float32")
        outfits[curr_hdu + nslits].data = out_var.astype("float32", casting="same_kind")
        outfits[curr_hdu + nslits].scale("float32")
    outfits[0].header.set("PYWIFES", __version__, "PyWiFeS version")
    outfits.writeto(outimg, overwrite=True)
    f3.close()
    return


def savitzky_golay(y, window_size, order, deriv=0, rate=1):
    """
     Smooth (and optionally differentiate) data with a Savitzky-Golay filter.
     The Savitzky-Golay filter removes high frequency noise from data.
     It has the advantage of preserving the original shape and
     features of the signal better than other types of filtering
     approaches, such as moving averages techniques.
     Parameters
     ----------
     y : array_like, shape (N,)
        the values of the time history of the signal.
    window_size : int
        the length of the window. Must be an odd integer number.
    order : int
        the order of the polynomial used in the filtering.
        Must be less then `window_size` - 1.
    deriv: int
        the order of the derivative to compute (default = 0 means only smoothing)
    Returns
    -------
    ys : ndarray, shape (N)
        the smoothed signal (or it's n-th derivative).
    Notes
    -----
    The Savitzky-Golay is a type of low-pass filter, particularly
    suited for smoothing noisy data. The main idea behind this
    approach is to make for each point a least-square fit with a
    polynomial of high order over a odd-sized window centered at
    the point.
    Examples
    --------
    t = np.linspace(-4, 4, 500)
    y = np.exp( -t**2 ) + np.random.normal(0, 0.05, t.shape)
    ysg = savitzky_golay(y, window_size=31, order=4)
    import matplotlib.pyplot as plt
    plt.plot(t, y, label='Noisy signal')
    plt.plot(t, np.exp(-t**2), 'k', lw=1.5, label='Original signal')
    plt.plot(t, ysg, 'r', label='Filtered signal')
    plt.legend()
    plt.show()
    References
    ----------
    .. [1] A. Savitzky, M. J. E. Golay, Smoothing and Differentiation of
       Data by Simplified Least Squares Procedures. Analytical
       Chemistry, 1964, 36 (8), pp 1627-1639.
    .. [2] Numerical Recipes 3rd Edition: The Art of Scientific Computing
       W.H. Press, S.A. Teukolsky, W.T. Vetterling, B.P. Flannery
       Cambridge University Press ISBN-13: 9780521880688
    """
    try:
        window_size = numpy.abs(int(window_size))
        order = numpy.abs(int(order))
    except ValueError:
        logger.error("window_size and order have to be of type int")
        raise
    if window_size % 2 != 1 or window_size < 1:
        logger.error("window_size size must be a positive odd number")
        raise
    if window_size < order + 2:
        logger.error("window_size is too small for the polynomials order")
        raise
    order_range = range(order + 1)
    half_window = (window_size - 1) // 2
    # precompute coefficients
    b = numpy.mat(
        [[k**i for i in order_range] for k in range(-half_window, half_window + 1)]
    )
    m = numpy.linalg.pinv(b).A[deriv] * rate**deriv * factorial(deriv)
    # pad the signal at the extremes with
    # values taken from the signal itself
    firstvals = y[0] - numpy.abs(y[1:half_window + 1][::-1] - y[0])
    lastvals = y[-1] + numpy.abs(y[-half_window - 1:-1][::-1] - y[-1])
    y = numpy.concatenate((firstvals, y, lastvals))
    return numpy.convolve(m[::-1], y, mode="valid")


# ------------------------------------------------------------------------
def derive_wifes_calibration(
    cube_fn_list,
    calib_out_fn,
    stdstar_name_list=None,
    extract_in_list=None,
    airmass_list=None,
    ref_dir=metadata_dir,
    ref_fname_list=None,
    plot_stars=False,
    plot_sensf=False,
    plot_dir=".",
    save_prefix="calib_",
    norm_stars=False,
    method="poly",
    polydeg=30,
    excise_cut=0.5,
    wave_min=None,
    wave_max=None,
    extinction_fn=None,
    ytrim=5,
    boxcar=11,
    debug=False,
):
    if debug:
        print(arguments())
    # get extinction curve
    if extinction_fn is None:
        extinct_interp = sso_extinct_interp
    else:
        ext_data = numpy.loadtxt(extinction_fn)
        extinct_interp = scipy.interpolate.interp1d(
            ext_data[:, 0], ext_data[:, 1], bounds_error=False, fill_value=numpy.nan
        )
        extinct_interp = scipy.interpolate.interp1d(
            ext_data[:, 0], ext_data[:, 1], bounds_error=False, fill_value=numpy.nan
        )
    # first extract stdstar spectra and compare to reference
    fratio_results = []
    for i in range(len(cube_fn_list)):
        cube_hdr = pyfits.getheader(cube_fn_list[i], ext=1)
        # ------------------------------------
        # figure out which star it is
        if stdstar_name_list is not None:
            star_name = stdstar_name_list[i]
            # if you forced an unknown star name, reset name to None
            if star_name not in ref_fname_lookup.keys():
                star_name = None
        else:
            star_name = None
        # try to find the nearest standard in the list
        if star_name is None:
            try:
                star_name, dist = find_nearest_stdstar(cube_fn_list[i])
                if dist > 200.0:
                    star_name = None
            except:
                # last resort: use the object name from the fits header
                # and pray it's correct
                star_name = cube_hdr["OBJECT"]
        # ------------------------------------
        print("Found star " + star_name)
        if airmass_list is not None:
            secz = airmass_list[i]

        else:
            try:
                secz = cube_hdr["AIRMASS"]
            except:
                print(
                    "AIRMASS header missing for {:s}".format(
                        cube_fn_list[i].split("/")[-1]
                    )
                )
                secz = 1.0

        # check if there is a calib spectrum...
        if ref_fname_list is not None:
            ref_fname = ref_fname_list[i]
        elif star_name in ref_fname_lookup.keys():
            ref_fname = ref_fname_lookup[star_name]
        else:
            continue

        # get observed data
        if extract_in_list is None:
            obs_wave, obs_flux = extract_wifes_stdstar(cube_fn_list[i], ytrim=ytrim)
        else:
            ex_data = numpy.loadtxt(extract_in_list[i])
            obs_wave = ex_data[:, 0]
            obs_flux = ex_data[:, 1]
        if wave_min is None:
            wave_min = numpy.min(obs_wave)
        if wave_max is None:
            wave_max = numpy.max(obs_wave)

        # get reference data
        ref_data = numpy.loadtxt(os.path.join(ref_dir, ref_fname))
        ref_interp = scipy.interpolate.interp1d(
            ref_data[:, 0], ref_data[:, 1], bounds_error=False, fill_value=numpy.nan
        )
        ref_flux = ref_interp(obs_wave)
        std_ext = extinct_interp(obs_wave)
        good_inds = numpy.nonzero(
            (numpy.isfinite(ref_flux))
            * (numpy.isfinite(std_ext))
            * (obs_wave >= wave_min)
            * (obs_wave <= wave_max)
            * (obs_flux > 0.0)
        )[0]
        init_flux_ratio = -2.5 * numpy.log10(obs_flux[good_inds] / ref_flux[good_inds])
        flux_ratio = init_flux_ratio + (secz - 1.0) * std_ext[good_inds]
        fratio_results.append([obs_wave[good_inds], flux_ratio])

        if plot_stars:
            scaled_flux = obs_flux[good_inds] / numpy.mean(10.0 ** (-0.4 * flux_ratio))
            plt.figure(1, figsize=(8, 5))
            plt.plot(obs_wave, ref_flux, color="b", label="Reference star flux")
            plt.plot(
                obs_wave[good_inds],
                scaled_flux,
                color="r",
                label="Scaled observed flux",
            )
            plt.title(star_name)
            plt.xlabel(r"Wavelength [$\AA$]")
            plt.legend()

            # Set y-limits to exclude peaks
            lower_limit = min(numpy.nanpercentile(scaled_flux, 0.2), numpy.nanmin(ref_flux))
            upper_limit = max(numpy.nanpercentile(scaled_flux, 99.8), numpy.nanmax(ref_flux))
            plt.ylim(lower_limit, upper_limit)
            plt.ylabel(r"Scaled Flux ")

            plot_name = f"{star_name}.png"
            plot_path = os.path.join(plot_dir, plot_name)
            plt.savefig(plot_path, dpi=300)
            plt.close()

    if len(fratio_results) < 1:
        # Didn't find any stars - there's no point in continuing
        print("Could not find flux calibration data for any stars. Skipping.")
        return

    # from all comparisons, derive a calibration solution
    # EVENTUALLY WILL FIT AN EXTINCTION TERM TOO
    if norm_stars:
        i_mid = int(len(fratio_results[0][0]) / 2)
        fscale_max = min([x[1][i_mid] for x in fratio_results])
        init_full_y = numpy.concatenate(
            [x[1] - x[1][i_mid] + fscale_max for x in fratio_results]
        )
    else:
        init_full_y = numpy.concatenate([x[1] for x in fratio_results])

    init_full_x = numpy.concatenate([x[0] for x in fratio_results])
    init_good_inds = numpy.nonzero(
        (numpy.isfinite(init_full_y))
        * (init_full_y < numpy.median(init_full_y) + 20.0)
        * (strong_telluric_mask(init_full_x))
        * (halpha_mask(init_full_x))
    )[0]
    # do a first fit
    next_full_y = init_full_y[init_good_inds]
    next_full_x = init_full_x[init_good_inds]
    sort_order = next_full_x.argsort()
    temp_full_x = next_full_x[sort_order]
    temp_full_y = next_full_y[sort_order]

    if method == "smooth_SG":
        # Savitzky-Golay requires continuous data. ->need to fill the 'holes'
        # It is a problem for red spectra (at this point at least)
        # Check if there are gaps (telluric, Halpha, etc ...)
        init_bad_inds = numpy.nonzero(
            1
            - (
                (numpy.isfinite(init_full_y))
                * (init_full_y < numpy.median(init_full_y) + 20.0)
                * (telluric_mask(init_full_x))
                * (halpha_mask(init_full_x))
            )
        )[0]
        if len(init_bad_inds) > 0:
            # if yes, first fit a polynomial, then use it to 'fill the gaps.
            temp_calib = numpy.polyfit(temp_full_x, temp_full_y, polydeg)
            temp_fvals = numpy.polyval(temp_calib, init_full_x)
            init_full_y[init_bad_inds] = temp_fvals[init_bad_inds]
            temp_full_y = init_full_y  # to ensure this case is then compatible
            temp_full_x = init_full_x
            # Fails if multiple stars ... need to order the array !
            this_sort_order = temp_full_x.argsort()
            temp_full_x = temp_full_x[this_sort_order]
            temp_full_y = temp_full_y[this_sort_order]
        # Then fit SG normally
        temp_fvals = savitzky_golay(temp_full_y, 101, 1, 0)
        excise_cut = 0.003
    else:
        temp_best_calib = numpy.polyfit(temp_full_x, temp_full_y, polydeg)
        temp_fvals = numpy.polyval(temp_best_calib, temp_full_x)
    # excise outliers
    final_good_inds = numpy.nonzero(
        numpy.abs(temp_fvals - temp_full_y) / numpy.abs(temp_fvals) < excise_cut
    )[0]
    full_x = temp_full_x[final_good_inds]
    full_y = temp_full_y[final_good_inds]

    if method == "smooth_SG":  # Fails if multiple stars ... need to order the array !
        X = numpy.copy(full_x)
        Y = numpy.copy(full_y)
        eps = 0.001  # We call two points the same in wavelength if they are closer than 0.001 A
        means = numpy.array(
            [(x, Y[numpy.abs(X - x) < eps].mean()) for x in numpy.unique(X)]
        )
        # Note that our array ends up sorted at the end of this because we use numpy.unique
        smooth_x = means[:, 0]
        smooth_y = numpy.pad(means[:, 1], boxcar, mode="edge")
        smooth_y = numpy.convolve(
            smooth_y, numpy.ones((boxcar,)) / boxcar, mode="same"
        )[boxcar:-boxcar]
        final_fvals = savitzky_golay(smooth_y, 101, 1, 0)
        this_f = scipy.interpolate.interp1d(
            smooth_x, final_fvals, bounds_error=False, kind="linear"
        )
        # all_final_fvals = this_f(init_full_x)
        final_x = full_x
        final_y = this_f(final_x)
    else:
        best_calib = numpy.polyfit(full_x, full_y, polydeg)
        this_f = numpy.poly1d(best_calib)

    best_calib = numpy.polyfit(full_x, full_y, polydeg)

    # Calculate the final result
    final_fvals = this_f(full_x)
    final_x = numpy.arange(
        numpy.min(full_x),
        1.000001 * numpy.max(full_x),
        0.0001 * (numpy.max(full_x) - numpy.min(full_x)),
    )
    final_y = this_f(final_x)

    # Plot Sensitivity function
    if plot_sensf:

        plt.figure(figsize=(8, 6))
        # MC update - raw fit on top
        plt.axes([0.10, 0.35, 0.85, 0.60])

        plt.plot(
            temp_full_x,
            temp_full_y,
            "r.",
            markerfacecolor="none",
            markeredgecolor="r",
            label="Raw sensitivity (initial regions)",
        )

        plt.plot(full_x, full_y, color="b", label="Raw sensitivity (valid regions)")

        plt.plot(temp_full_x, temp_fvals, color=r"#FF6103", lw=2, label="Initial fit")

        if method == "smooth_SG":
            plt.plot(
                means[:, 0],
                means[:, 1],
                color="b",
                label="Mean sensitivity (valid regions, all stars)",
            )
            plt.plot(
                smooth_x, smooth_y, color=r"#7f007f", label="Smoothed mean sensitivity"
            )
        else:
            plt.plot(
                full_x, full_y, color="b", label="Raw sensitivity (valid regions)"
            )
        plt.plot(full_x, final_fvals, color=r"#00FF00", lw=2, label="Final fit")

        plt.xlim([numpy.min(full_x), numpy.max(full_x)])
        curr_ylim = plt.ylim()
        curr_xlim = plt.xlim()
        plt.ylim(curr_ylim[::-1])

        plt.ylabel("Counts-to-Flux Ratio [mag]")

        plt.title("Derived sensitivity function")
        plt.legend(loc="lower right", fancybox=True, shadow=True)
        # lower plot - residuals!
        plt.axes([0.10, 0.10, 0.85, 0.25])
        plt.plot(
            full_x,
            full_y - final_fvals,
            "k.",
            mec=r"#666666",
            markerfacecolor="none",
            label="Residuals",
        )
        plt.axhline(0.0, color="k")
        plt.xlim(curr_xlim)
        plt.ylim([-0.2, 0.2])
        plt.xlabel(r"Wavelength [$\AA$]")
        plt.ylabel("Residuals")

        plot_name = "flux_calibration_solution.png"
        plot_path = os.path.join(plot_dir, plot_name)
        plt.savefig(plot_path, dpi=300)
        plt.close()

    save_calib = {"wave": final_x, "cal": final_y, "std_file": ref_fname}
    f1 = open(calib_out_fn, "wb")
    pickle.dump(save_calib, f1)
    f1.close()
    return


# ------------------------------------------------------------------------
def calibrate_wifes_cube(inimg, outimg, calib_fn, mode="pywifes", extinction_fn=None, interactive_plot=False):

    if not os.path.isfile(calib_fn):
        print(f"No flux calibration file {os.path.basename(calib_fn)}. Outputting uncalibrated cube.")
        imcopy(inimg, outimg)
        return

    if is_halfframe(inimg):
        if is_taros(inimg):
            nslits = 12
        else:
            nslits = 13
    else:
        nslits = 25

    # get extinction curve
    if extinction_fn is None:
        extinct_interp = sso_extinct_interp
    else:
        ext_data = numpy.loadtxt(extinction_fn)
        extinct_interp = scipy.interpolate.interp1d(
            ext_data[:, 0], ext_data[:, 1], bounds_error=False, fill_value=numpy.nan
        )
    # open data
    f3 = pyfits.open(inimg)
    # get the wavelength array
    wave0 = f3[1].header["CRVAL1"]
    dwave = f3[1].header["CDELT1"]
    exptime = f3[1].header["EXPTIME"]
    try:
        secz = f3[1].header["AIRMASS"]
    except:
        secz = 1.0
        print("AIRMASS keyword not found, assuming airmass=1.0")
    nlam = numpy.shape(f3[1].data)[1]
    wave_array = wave0 + dwave * numpy.arange(nlam, dtype="d")
    std_file = "None"
    # calculate the flux calibration array
    if mode == "pywifes":
        f1 = open(calib_fn, "rb")
        calib_info = pickle.load(f1)
        f1.close()
        sort_order = calib_info["wave"].argsort()
        calib_wave = calib_info["wave"][sort_order]
        calib_flux = calib_info["cal"][sort_order]
        std_file = calib_info["std_file"]
        calib_interp = scipy.interpolate.interp1d(
            calib_wave, calib_flux, bounds_error=False, fill_value=-100.0, kind="linear"
        )
        all_final_fvals = calib_interp(wave_array)
        inst_fcal_array = 10.0 ** (-0.4 * all_final_fvals)
    elif mode == "iraf":
        f = pyfits.open(calib_fn)
        calib_wave = f[0].header["CRVAL1"] + f[0].header["CDELT1"] * numpy.arange(
            f[0].header["NAXIS1"], dtype="d"
        )
        calib_flux = f[0].data
        calib_interp = scipy.interpolate.interp1d(
            calib_wave, calib_flux, bounds_error=False, fill_value=0.0
        )
        inst_fcal_array = calib_interp(wave_array)
        f.close()
        std_file = os.path.basename(calib_fn)
    else:
        raise ValueError("Calibration mode not defined")
    if interactive_plot:
        plt.plot(calib_wave, calib_flux, label='calib')
        plt.scatter(wave_array, inst_fcal_array, label='interpolated')
        plt.title(f"Standard star - {std_file}")
        plt.legend()
        plt.show()
    # calculate extinction curve for observed airmass
    obj_ext = 10.0 ** (-0.4 * ((secz - 1.0) * extinct_interp(wave_array)))
    fcal_array = inst_fcal_array * obj_ext
    # apply flux cal to data!
    outfits = pyfits.HDUList(f3)
    for i in range(nslits):
        curr_hdu = i + 1
        curr_flux = f3[curr_hdu].data
        curr_var = f3[curr_hdu + nslits].data
        out_flux = curr_flux / (fcal_array * exptime * dwave)
        out_var = curr_var / ((fcal_array * exptime * dwave) ** 2)
        # save to data cube
        outfits[curr_hdu].data = out_flux.astype("float32", casting="same_kind")
        outfits[curr_hdu].scale("float32")
        outfits[curr_hdu + nslits].data = out_var.astype("float32", casting="same_kind")
        outfits[curr_hdu + nslits].scale("float32")
    outfits[0].header.set("PYWIFES", __version__, "PyWiFeS version")
    outfits[0].header.set("PYWFCALM", mode, "PyWiFeS: flux calibration mode")
    if extinction_fn is None:
        outfits[0].header.set("PYWFCALX", 'Standard SSO', "PyWiFeS: flux calibration extinction model")
    else:
        outfits[0].header.set("PYWFCALX", extinction_fn.split("/")[-1],
                              "PyWiFeS: flux calibration extinction model")
    outfits[0].header.set("PYWFSTDF", std_file, "PyWiFeS: standard star file for flux calibration")
    outfits.writeto(outimg, overwrite=True)
    f3.close()
    return


# ------------------------------------------------------------------------
# telluric corrections!!!
def derive_wifes_telluric(
    cube_fn_list,
    out_fn,
    plot=True,
    plot_stars=False,
    plot_dir=None,
    save_prefix="telluric",
    extract_in_list=None,
    airmass_list=None,
    telluric_threshold=0.97,
    fit_wmin=5400.0,
    fit_wmax=10000.0,
    H2O_power=0.72,
    O2_power=0.40,
    polydeg=4,
    ytrim=3,
    debug=False,
):
    if debug:
        print(arguments())
    # ---------------------------------------------
    # for each star, get its airmass if not specified in input
    if airmass_list is None:
        airmass_list = []
        for fn in cube_fn_list:
            try:
                f = pyfits.open(fn)
                new_am = float(f[1].header["AIRMASS"])
                f.close()
            except:
                new_am = 1.0
                print("AIRMASS keyword not found, assuming 1.0")
            airmass_list.append(new_am)
    # ---------------------------------------------
    # now extract each star spectrum and derive telluric correction spectra
    O2_corrections = []
    H2O_corrections = []
    tellstd_list = []
    for i in range(len(cube_fn_list)):
        # get extracted spectrum
        if extract_in_list is None:
            obs_wave, obs_flux = extract_wifes_stdstar(cube_fn_list[i], ytrim=ytrim)
            tellhdr = pyfits.getheader(cube_fn_list[i])
            if "OBJECT" in tellhdr:
                tellstd_list.append(tellhdr["OBJECT"])
        else:
            ex_data = numpy.loadtxt(extract_in_list[i])
            obs_wave = ex_data[:, 0]
            obs_flux = ex_data[:, 1]

        # define all the telluric regions
        O2_mask = wavelength_mask(obs_wave, O2_telluric_bands)
        H2O_mask = wavelength_mask(obs_wave, H2O_telluric_bands)
        O2_inds = numpy.nonzero(O2_mask == 0)[0]
        H2O_inds = numpy.nonzero(H2O_mask == 0)[0]
        # fit smooth polynomial to non-telluric regions!
        fit_inds = numpy.nonzero(
            O2_mask * H2O_mask * (obs_wave >= fit_wmin) * (obs_wave <= fit_wmax)
        )[0]

        smooth_poly = numpy.polyfit(obs_wave[fit_inds], obs_flux[fit_inds], polydeg)
        # get ratio of data to smooth continuum
        smooth_cont = numpy.polyval(smooth_poly, obs_wave)
        init_ratio = obs_flux / smooth_cont

        # isolate desired regions, apply thresholds!
        O2_ratio = numpy.ones(len(obs_wave), dtype="d")
        O2_ratio[O2_inds] = init_ratio[O2_inds]
        O2_ratio[numpy.nonzero(O2_ratio >= telluric_threshold)[0]] = 1.0
        O2_corrections.append([obs_wave, O2_ratio])
        H2O_ratio = numpy.ones(len(obs_wave), dtype="d")
        H2O_ratio[H2O_inds] = init_ratio[H2O_inds]
        H2O_ratio[numpy.nonzero(H2O_ratio >= telluric_threshold)[0]] = 1.0
        H2O_corrections.append([obs_wave, H2O_ratio])

    if len(tellstd_list) == 0 and len(extract_in_list) == 0:
        # Didn't find any stars - there's no point in continuing
        print("Could not find telluric calibration data for any stars. Skipping.")
        return

    # ---------------------------------------------
    # now using all, derive the appropriate solutions!
    tellstd_list = numpy.unique(numpy.array(tellstd_list))

    # wavelength range shouldn't change much, use the first one!
    base_wave = O2_corrections[0][0]
    O2_corr_temp = numpy.zeros([len(cube_fn_list), len(base_wave)], dtype="d")
    H2O_corr_temp = numpy.zeros([len(cube_fn_list), len(base_wave)], dtype="d")
    O2_corr_temp[0, :] = O2_corrections[0][1]
    H2O_corr_temp[0, :] = (H2O_corrections[0][1]) ** (1.0 / (airmass_list[0] ** 0.55))
    for i in range(1, len(cube_fn_list)):
        O2_interp = scipy.interpolate.interp1d(
            O2_corrections[i][0],
            (O2_corrections[i][1]) ** (1.0 / (airmass_list[i] ** O2_power)),
            bounds_error=False,
            fill_value=1.0,
        )
        O2_corr_temp[i, :] = O2_interp(base_wave)
        H2O_interp = scipy.interpolate.interp1d(
            H2O_corrections[i][0],
            (H2O_corrections[i][1]) ** (1.0 / (airmass_list[i] ** H2O_power)),
            bounds_error=False,
            fill_value=1.0,
        )
        H2O_corr_temp[i, :] = H2O_interp(base_wave)
    final_O2_corr = numpy.mean(O2_corr_temp, axis=0)
    final_H2O_corr = numpy.mean(H2O_corr_temp, axis=0)
    # fix zero values
    final_O2_corr[numpy.nonzero(final_O2_corr < 0.01)[0]] = 0.01
    final_H2O_corr[numpy.nonzero(final_H2O_corr < 0.01)[0]] = 0.01
    # fix nan values
    final_O2_corr[numpy.nonzero(final_O2_corr != final_O2_corr)[0]] = 1.0
    final_H2O_corr[numpy.nonzero(final_H2O_corr != final_H2O_corr)[0]] = 1.0
    # ---------------------------------------------
    # Check Plot
    if plot:
        fig, (ax_top, ax_bottom) = plt.subplots(2, 1, sharex=True, figsize=(10, 8))
        plt.suptitle("Telluric Correction Function", size=16)

        # Top subplot (Telluric start)
        ax_top.plot(obs_wave, obs_flux, "C0", label="Observed Flux")
        ax_top.plot(obs_wave, smooth_cont, "r", ls="dashed", label="Smooth Fitting")
        ax_top.legend()
        ax_top.set_ylabel(r"Flux [$F_{\lambda}$]")

        # Set y-limits to exclude peaks
        lower_limit = numpy.percentile(obs_flux, 0.2)
        upper_limit = numpy.percentile(obs_flux, 99.8)
        ax_top.set_ylim(lower_limit, upper_limit)

        # Bottom subplot (Telluric correction derived)
        # Mask the continum for plotting
        telluric_correction = final_O2_corr * final_H2O_corr

        ax_bottom.plot(
            base_wave,
            telluric_correction,
            color="k",
            lw=1,
            label=r"Telluric correction",
        )
        # Shading the masked regions for O2 and H2O corrections
        ax_bottom.fill_between(
            base_wave,
            final_O2_corr,
            where=(final_O2_corr < 1),
            lw=0,
            color="C4",
            alpha=0.5,
            label=r"O$_2$ lines",
        )
        ax_bottom.fill_between(
            base_wave,
            final_H2O_corr,
            where=(final_H2O_corr < 1),
            lw=0,
            color="C0",
            alpha=0.5,
            label=r"H$_2$O lines",
        )

        # for i, cube_fn in enumerate(cube_fn_list):
        #     airmass = airmass_list[i]
        #     wave, O2_ratio = O2_corrections[i]
        #     H2O_ratio = H2O_corrections[i][1]

        #     ax_bottom.plot(wave, O2_ratio**(1.0/(airmass**O2_power)), label=f'{cube_fn} O2')
        #     ax_bottom.plot(wave, H2O_ratio**(1.0/(airmass**H2O_power)), label=f'{cube_fn} H2O')

        ax_bottom.set_xlabel(r"Wavelength [$\AA$]")
        ax_bottom.set_ylabel("Transmission at Airmass = 1")
        ax_bottom.legend()

        # Set x-axis limits
        ax_bottom.set_xlim([numpy.min(base_wave), numpy.max(base_wave)])

        # Display the plot
        plt.tight_layout()

        plot_name = f"{save_prefix}_correction.png"
        plot_path = os.path.join(plot_dir, plot_name)
        plt.savefig(plot_path, dpi=300)
        plt.close()

    # ---------------------------------------------
    # save to output file!
    tellcorr_info = {
        "wave": base_wave,
        "O2": final_O2_corr,
        "H2O": final_H2O_corr,
        "O2_power": O2_power,
        "H2O_power": H2O_power,
        "tellstd_list": tellstd_list,
    }
    f1 = open(out_fn, "wb")
    pickle.dump(tellcorr_info, f1)
    f1.close()
    return


def apply_wifes_telluric(inimg, outimg, tellcorr_fn, airmass=None):

    if not os.path.isfile(tellcorr_fn):
        print(f"No telluric calibration file {os.path.basename(tellcorr_fn)}. Outputting uncalibrated cube.")
        imcopy(inimg, outimg)
        return

    halfframe = is_halfframe(inimg)
    if halfframe:
        if is_taros(inimg):
            # first = 1
            # last = 12
            nslits = 12
        else:
            # first = 7
            # last = 19
            nslits = 13
    else:
        # first = 1
        # last = 25
        nslits = 25

    # ---------------------------------------------
    # open the telluric corrction file
    f1 = open(tellcorr_fn, "rb")
    tellcorr_info = pickle.load(f1)
    if "tellstd_list" in tellcorr_info:
        tellstd_list = tellcorr_info["tellstd_list"]
        tellstd_list = ",".join(str(tf) for tf in tellstd_list)
    else:
        tellstd_list = "None"
    O2_interp = scipy.interpolate.interp1d(
        tellcorr_info["wave"], tellcorr_info["O2"], bounds_error=False, fill_value=1.0
    )
    H2O_interp = scipy.interpolate.interp1d(
        tellcorr_info["wave"], tellcorr_info["H2O"], bounds_error=False, fill_value=1.0
    )
    try:
        O2_power = tellcorr_info["O2_power"]
        H2O_power = tellcorr_info["H2O_power"]
    except:
        O2_power = 0.55
        H2O_power = 1.0
    f1.close()
    # ---------------------------------------------
    # apply to chosen data
    f3 = pyfits.open(inimg)
    # get airmass
    if airmass is None:
        try:
            airmass = float(f3[1].header["AIRMASS"])
        except:
            airmass = 1.0
            print("AIRMASS keyword not found, assuming airmass=1.0")
    # get the wavelength array
    wave0 = f3[1].header["CRVAL1"]
    dwave = f3[1].header["CDELT1"]
    nlam = numpy.shape(f3[1].data)[1]
    wave_array = wave0 + dwave * numpy.arange(nlam, dtype="d")
    # calculate the telluric correction array
    base_O2_corr = O2_interp(wave_array)
    O2_corr = base_O2_corr ** (airmass**O2_power)
    base_H2O_corr = H2O_interp(wave_array)
    H2O_corr = base_H2O_corr ** (airmass**H2O_power)
    fcal_array = O2_corr * H2O_corr
    # correct the data
    outfits = pyfits.HDUList(f3)
    for i in range(nslits):
        curr_hdu = i + 1
        curr_flux = f3[curr_hdu].data
        curr_var = f3[curr_hdu + nslits].data
        out_flux = curr_flux / fcal_array
        out_var = curr_var / (fcal_array**2)
        # save to data cube
        outfits[curr_hdu].data = out_flux.astype("float32", casting="same_kind")
        outfits[curr_hdu + nslits].data = out_var.astype("float32", casting="same_kind")
    outfits[0].header.set("PYWIFES", __version__, "PyWiFeS version")
    outfits[0].header.set("PYWTSTDF", tellstd_list, "PyWiFeS: telluric standard star filename(s)")
    outfits.writeto(outimg, overwrite=True)
    f3.close()
    return
