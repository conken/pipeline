import sys
import os
from astropy.io import fits
from . import wifes_calib
import pandas as pd
import re

def get_obs_metadata(filenames,data_dir):
    stdstar_list = wifes_calib.ref_fname_lookup.keys()

    # classify each obs
    bias = []
    domeflat = []
    twiflat = []
    dark = []
    arc = []
    wire = []
    stdstar = {}
    science = {}

    for filename in filenames:        
        basename = filename.replace('.fits', '')

        f = fits.open(data_dir + filename)
        imagetype = f[0].header['IMAGETYP'].upper()
        obj_name = f[0].header['OBJECT']
        f.close()
        #---------------------------
        # check if it is within a close distance to a standard star
        # if so, fix the object name to be the good one from the list!
        try:
            near_std, std_dist = wifes_calib.find_nearest_stdstar(data_dir + filename)
            if std_dist < 100.0:
                obj_name = near_std
        except:
            pass
        #---------------------------
        # 1 - bias frames
        if imagetype == 'BIAS':
            bias.append(basename)
        # 2 - quartz flats
        if imagetype == 'FLAT':
            domeflat.append(basename)
        # 3 - twilight flats
        if imagetype == 'SKYFLAT':
            twiflat.append(basename)
        # 4 - dark frames
        if imagetype == 'DARK':
            dark.append(basename)
        # 5 - arc frames
        if imagetype == 'ARC':
            arc.append(basename)
        # 6 - wire frames
        if imagetype == 'WIRE':
            wire.append(basename)
        # 7 - standard star
        if imagetype == 'STANDARD':
            # group standard obs together!
            if obj_name in stdstar.keys():
                stdstar[obj_name].append(basename)
            else:
                stdstar[obj_name] = [basename]
        
        # all else are science targets (also consider standar star in imagety = OBJECT)
        if imagetype == 'OBJECT':
            if obj_name in stdstar_list:
                # group standard obs together!
                if obj_name in stdstar.keys():
                    stdstar[obj_name].append(basename)
                else:
                    stdstar[obj_name] = [basename]
            else:
                # group science obs together!
                if obj_name in science.keys():
                    science[obj_name].append(basename)
                else:
                    science[obj_name] = [basename]

    # #------------------
    # science dictionay

    sci_obs = []

    for obj_name in science.keys():
        obs_list = science[obj_name]
        sci_obs.append({'sci':obs_list, 'sky':[]})


    #------------------
    # stdstars dictionary
    std_obs = []

    for obj_name in stdstar.keys():
        obs_list = stdstar[obj_name]
        std_obs.append({'sci':obs_list, 'name':obj_name,'type':['flux', 'telluric']})


    obs_metadata = {
        'bias' : bias,
        'domeflat' : domeflat,
        'twiflat' : twiflat,
        'dark' : dark,
        'wire' : wire,
        'arc'  : arc,
        'sci'  : sci_obs,
        'std'  : std_obs}
    
    return obs_metadata 



def classify(data_dir, naxis2_to_process = 0):
    # Get list of all fits files in directory
    filenames = os.listdir(data_dir)

    # Filtering the data as per blue and red arm
    blue_filenames = []
    red_filenames = []

    for filename in filenames:
        try:
            f = fits.open(data_dir+filename)
            camera = f[0].header['CAMERA']
            naxis2 = f[0].header['NAXIS2']
            f.close()
        except:
            continue
        if naxis2_to_process != 0 and naxis2_to_process != naxis2:
            continue
        if camera == 'WiFeSBlue':
            if filename in blue_filenames:
                continue
            else:
                blue_filenames.append(filename)
        if camera == 'WiFeSRed':
            if filename in red_filenames:
                continue
            else:
                red_filenames.append(filename)

    blue_obs_metadata = get_obs_metadata(blue_filenames, data_dir)
    red_obs_metadata = get_obs_metadata(red_filenames, data_dir)

    return {"blue": blue_obs_metadata, "red": red_obs_metadata}







def extract_ut_part(path):
    if path == None:
        return None
    
    # Define the pattern to match
    pattern = r'UT.*?(?=\..*?\.fits)'

    # Use re.search() to find the first occurrence of the pattern in the string
    match = re.search(pattern, path)

    # If a match is found, extract the matched substring
    if match:
        ut_part = match.group(0)
        return ut_part
    else:
        return None

def cube_matcher(paths_list):
    date_obs_list = []
    for path in paths_list:
        date_obs_list.append(fits.getheader(path)['DATE-OBS'])

    df = pd.DataFrame({'path': paths_list, 'date_obs': date_obs_list})
    
    matched_paths = df.groupby('date_obs')['path'].apply(list).tolist()

    matched_dicts = []
    
    for paths in matched_paths:
            matched_dict = {'Blue': None, 'Red': None, 'file_name': None}
            for path in paths:
                arm = fits.getheader(path)['ARM']
                matched_dict[arm] = path
                matched_dict['file_name'] = extract_ut_part(path)
            matched_dicts.append(matched_dict)
     
    return matched_dicts






