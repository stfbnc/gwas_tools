#  scattered_light_raw.py - this file is part of the gwadaptive_scattering package.
#  Copyright (C) 2020- Stefano Bianchi
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <https://www.gnu.org/licenses/>.


import os
import numpy as np
from ..utils import signal_utils, file_utils
from ..common import defines


def scattered_light_raw(gps, seconds, target_channel_name, channels_file, out_path, f_lowpass,
                        event="center", fs=256, n_scattering=1, smooth_win=50,
                        save_data=True, check_lock=False):
    """Analysis for scattered light identification using raw target channel and not its imfs.
    The script outputs a folder named as the input gps,
    with inside two files:
        - most correlated predictor (*.predictors, optional)
        - output.yml, a summary of the analysis' results

    Parameters
    ----------
    gps : int
        gps of the event
    seconds : int
        how many seconds to analyze in total
    target_channel_name : str
        target channel name
    channels_file : str
        channels list
    out_path : str
        output path where to save results
    f_lowpass : float or str
        lowpass filter frequency
    event : str
        position of the event's gps in the analysed period.
        Can be `start`, `center`, or `end` (default : `center`)
    fs : float, optional
        channels resample frequency (default : 256)
    n_scattering : int, optional
        number of signal bounces (default : 1)
    smooth_win : int, optional
        signals smoothing window (default : 50)
    save_data : bool, optional
        if True, instantaneous amplitudes and predictors are saved to file (defaults : True)
    check_lock : bool, optional
        if True, lock channel status is checked, and if it is not always locked, the analysis is not performed (default : False)
    """
    if event not in defines.EVENT_LOCATION:
        raise ValueError("Event time can only be: {}".format(", ".join(defines.EVENT_LOCATION)))
    if not isinstance(f_lowpass, int) and not isinstance(f_lowpass, float) and f_lowpass not in defines.LOWP_FREQ_OPTS:
        raise ValueError("Lowpass frequency must be a float or one of these "
                         "strings : {}".format(", ".join(defines.LOWP_FREQ_OPTS)))

    # initialize variables
    ch_f = open(channels_file, "r")
    channels_list = [ch.rstrip() for ch in ch_f.readlines() if ch.strip()]
    ch_f.close()

    # create folder for results if it does not exist
    odir_name = "{:d}".format(gps)
    out_path = os.path.join(out_path, odir_name)
    if not os.path.isdir(out_path):
        os.makedirs(out_path, exist_ok=True)

    gps_start, gps_end = signal_utils.get_gps_interval_extremes(gps, seconds, event)
    ifo = signal_utils.get_ifo_of_channel(target_channel_name)

    if check_lock:
        lock_channel_name = signal_utils.get_lock_channel_name_for_ifo(ifo)
        if lock_channel_name is not None:
            lock_channel_data = signal_utils.get_instrument_lock_data(lock_channel_name, gps_start, gps_end)
            if ifo == "L1":
                if len(lock_channel_data) != 1 or lock_channel_data[0][0] != gps_start or lock_channel_data[0][-1] != gps_end:
                    return None
            elif ifo == "V1":
                if not np.all(lock_channel_data == 1):
                    return None

    # build time series matrix
    data, fs = signal_utils.get_data_from_gwf_files("/sps/virgo/BKDB/O3/O3_raw.ffl", "-", 2, 3,
                                                    target_channel_name, channels_list,
                                                    gps_start, gps_end, fs, verbose=True)

    # predictors
    predictor = signal_utils.get_predictors(data[:, 1:], fs, smooth_win=smooth_win, n_scattering=n_scattering)

    # compute lowpass frequency in case it is a string
    if isinstance(f_lowpass, str):
        if f_lowpass == "average":
            f_lowpass = np.max([np.mean(predictor[:, i]) for i in range(predictor.shape[1])])
        elif f_lowpass == "max":
            f_lowpass = np.max([np.max(predictor[:, i]) for i in range(predictor.shape[1])])

    # target channel
    target_channel = signal_utils.butter_lowpass_filter(data[:, 0], f_lowpass, fs)

    # correlations
    corrs = np.zeros((predictor.shape[1], ), dtype=float)
    for l in range(predictor.shape[1]):
        corrs[l] = signal_utils.get_correlation_between(predictor[:, l], target_channel)

    # max correlations
    max_val = np.max(corrs)
    max_channel = np.argmax(corrs)
    m_freq = signal_utils.mean_frequency(channels_list[max_channel], gps_start, gps_end, bandpass_limits=(0.03, 10))

    # output file
    out_file = file_utils.YmlFile()
    out_file.write_parameters(gps, seconds, event, target_channel_name, channels_file,
                              out_path, fs, f_lowpass, n_scattering, smooth_win)
    out_file.write_correlation_section([channels_list[max_channel]], [max_val], [m_freq])
    out_file.save(out_path)

    if save_data:
        # save predictors
        selected_predictors = predictor[:, max_channel]
        file_utils.save_predictors(selected_predictors, "_".join(target_channel_name.split(":")), out_path)
