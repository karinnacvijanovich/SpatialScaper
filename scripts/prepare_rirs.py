import os
import math
import random
import argparse
import shutil
import requests
import zipfile
import librosa
import numpy as np
import soundfile as sf
from pathlib import Path
import pysofaconventions as pysofa

from utils import download_file, extract_zip, combine_multizip
from spatialscaper import sofa_utils, tau_utils

FS = 24000

METU_REMOTES = {
    "spargair.zip": "https://zenodo.org/record/2635758/files/spargair.zip",
}

TAU_REMOTES = {
    "TAU-SRIR_DB.z01": "https://zenodo.org/records/6408611/files/TAU-SRIR_DB.z01?download=1",
    "TAU-SRIR_DB.z02": "https://zenodo.org/records/6408611/files/TAU-SRIR_DB.z02?download=1",
    "TAU-SRIR_DB.z03": "https://zenodo.org/records/6408611/files/TAU-SRIR_DB.z03?download=1",
    "TAU-SRIR_DB.zip": "https://zenodo.org/records/6408611/files/TAU-SRIR_DB.zip?download=1",
    "TAU-SNoise_DB.z01": "https://zenodo.org/records/6408611/files/TAU-SNoise_DB.z01?download=1",
    "TAU-SNoise_DB.zip": "https://zenodo.org/records/6408611/files/TAU-SNoise_DB.zip?download=1",
}

ARNI_REMOTES = {
    "6dof_SRIRs_eigenmike_raw.zip": "https://zenodo.org/records/5720724/files/6dof_SRIRs_eigenmike_raw.zip",
    "6dof_SRIRs_eigenmike_SH.zip": "https://zenodo.org/records/5720724/files/6dof_SRIRs_eigenmike_SH.zip",
}

MOTUS_REMOTES = {
    "raw_rirs.zip": "https://zenodo.org/records/4923187/files/raw_rirs.zip",
    "sh_rirs.zip": "https://zenodo.org/records/4923187/files/sh_rirs.zip",
    "metadata.zip": "https://zenodo.org/records/4923187/files/metadata.zip",
}

NTAU_ROOMS = 9

METU_DB_NAME = "METU-SPARG"
TAU_DB_NAME = "TAU-SRIR-DB-SOFA"
ARNI_DB_NAME = "ARNI-SRIR-DB-SOFA"
MOTUS_DB_NAME = "MOTUS" 

__TETRA_CHANS_IN_EM32__ = [5, 9, 25, 21]
__FOA_ACN_CHANS__ = [0, 1, 2, 3] 


def create_single_sofa_file(aud_fmt, tau_db_dir, sofa_db_dir, db_name):
    db_dir = sofa_db_dir
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    for room_idx in range(NTAU_ROOMS):
        # Load flattened (and flipped) rirs/paths from TAU-SRIR database
        rirs, source_pos, mic_pos, room = sofa_utils.load_flat_tau_srir(
            tau_db_dir, room_idx, aud_fmt=aud_fmt
        )
        
        filepath = os.path.join(db_dir, f"{room}_{aud_fmt}.sofa")
        comment = f"SOFA conversion of {room} from TAU-SRIR-DB"

        print(
            f"Creating .sofa file for {aud_fmt}, Room: {room} (Progress: {room_idx + 1}/9)"
        )

        # Create .sofa files with flattened rirs/paths + metadata
        sofa_utils.create_srir_sofa(
            filepath,
            rirs,
            source_pos,
            mic_pos,
            db_name=db_name,
            room_name=room,
            listener_name=aud_fmt,
            sr=FS,
            comment=comment,
        )


def download_and_extract_remotes(urls_dict, extract_to):
    # Ensure the extract_to directory exists
    extract_to = Path(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)

    # Extract the filename from the URL
    for filename, url in urls_dict.items():
        zip_path = extract_to / filename
        # Check if the extracted directory already exists
        extracted_dir = extract_to / filename.replace(".zip", "")
        if extracted_dir.is_dir() or zip_path.is_file():
            print(
                f"Data already present in {extracted_dir}. Skipping download and extraction."
            )
        else:
            # Download and extract the file
            download_file(url, zip_path)
            extract_zip(zip_path, extract_to)
    
            # remove the zip file after extraction
            os.remove(zip_path)


def prepare_metu(dataset_path, dest_path_sofa):
    spargpath = Path(dataset_path) / "spargair" / "em32"
    XYZs = os.listdir(spargpath)

    def XYZ_2_xyz(XYZ):
        X, Y, Z = XYZ
        x = (3 - int(X)) * 0.5
        y = (3 - int(Y)) * 0.5
        z = (int(Z) - 2) * 0.5
        return x, y, z

    IRs = []
    xyzs = []
    for XYZ in XYZs:
        xyz = XYZ_2_xyz(XYZ)
        xyzs.append(xyz)

        wavpath = spargpath / XYZ
        X = []
        for ichan in __TETRA_CHANS_IN_EM32__:  # Specific channels for 'mic' format
            wavfile = wavpath / f"IR{ichan+1:05d}.wav"
            x, sr = sf.read(wavfile)
            X.append(x)
        IRs.append(np.array(X))

    filepath = dest_path_sofa / "metu_sparg_mic.sofa"
    rirs = np.array(IRs)
    source_pos = np.array(xyzs)
    mic_pos = np.array([[0, 0, 0]])

    sofa_utils.create_srir_sofa(
        filepath,
        rirs,
        source_pos,
        mic_pos,
        db_name= METU_DB_NAME,
        room_name="classroom",
        listener_name="em32",
        sr=sr,
    )

def prepare_motus(dataset_path, dest_path_sofa, audio_fmts = ["foa","mic"]):
    # script_dir = os.path.dirname(os.path.abspath(__file__))
    # os.chdir(os.path.dirname(script_dir))
    source_positions = {
        '1': np.array([[1.637, 0.0, 0.0]]),
        '2': np.array([[-0.078, 1.663, 0.0]]),
        '3': np.array([[0.658, 1.22, 0.0]]),
        '4': np.array([[2.056, 1.362, 0.0]])
    }
    mic_pos = np.array([[0.0, 0.0, 0.0]])
    
    for fmt in audio_fmts: 
        if fmt == "foa": 
            motuspath = Path(dataset_path) / "sh_rirs"
        elif fmt == "mic": 
            motuspath = Path(dataset_path) / "raw_rirs"
        RIR_file_names = os.listdir(motuspath)
        IRs, xyzs = [], []
        for filename in RIR_file_names:
            source_pos_index = filename.split("_")[1]
            source_pos = source_positions[source_pos_index] + random.uniform(-0.001, 0.001)
            xyzs.append(source_pos)
            wavfile = motuspath / filename
            x, sr = sf.read(wavfile)
            if aud_fmt == "foa": 
                x = x[:, __FOA_ACN_CHANS__] 
            else:
                x = x[:, __TETRA_CHANS_IN_EM32__]   
            IRs.append(x)
        rirs = np.array(IRs)
        # Reshape source_pos to have shape (num_measurements, 3) as required in sofa_utils
        # (M,C) aka... (num measurements, num coordinates)
        source_pos = np.array(xyzs).reshape(len(xyzs), 3)
        filepath = dest_path_sofa / f"motusroom_{aud_fmt}.sofa"
        #print("Reached the point of creating the SOFA file.")
        sofa_utils.create_srir_sofa(
            filepath,
            rirs,
            source_pos,
            mic_pos,
            db_name= MOTUS_DB_NAME, 
            room_name="motus_room",
            listener_name=aud_fmt,
            sr=sr,
        )

def download_tau(dest_path):
    # Download combine and extract zip files
    for filename, url in TAU_REMOTES.items():
        download_file(url, dest_path / filename)
    combine_multizip(f"{dest_path/'TAU-SRIR_DB.zip'}", f"{dest_path/'single.zip'}")
    extract_zip(dest_path / "single.zip", dest_path)
    combine_multizip(f"{dest_path/'TAU-SNoise_DB.zip'}", f"{dest_path/'single.zip'}")
    extract_zip(dest_path / "single.zip", dest_path)


def prepare_tau(path_raw, path_sofa, formats=["foa", "mic"]):
    # generate Sofa files
    tau_db_dir = f"{path_raw/'TAU-SRIR_DB'}"
    sofa_db_dir = path_sofa
    for aud_fmt in formats:
        print(f"Starting .sofa creation for {aud_fmt} format.")
        create_single_sofa_file(aud_fmt, tau_db_dir, sofa_db_dir, TAU_DB_NAME)
        print(f"Finished .sofa creation for {aud_fmt} format.")


def compute_azimuth_elevation(receiver_pos, source_pos):
    # Calculate the vector from the receiver to the source
    vector = [
        source_pos[0] - receiver_pos[0],
        source_pos[1] - receiver_pos[1],
        source_pos[2] - receiver_pos[2],
    ]
    # Calculate the azimuth angle
    azimuth = math.atan2(vector[0], vector[1])
    # Calculate the elevation angle
    distance = math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)
    elevation = math.asin(vector[2] / distance)
    return azimuth, elevation, distance


def get_absorption_level_arni(filename):
    return int(filename.split("_")[4].replace("percent", ""))


def center_and_translate_arni(receiver_pos, source_pos):
    # Given two points, center the receiver coordinate at zero and tranlate the source
    y1, x1, z1 = receiver_pos[0], receiver_pos[1], receiver_pos[2]
    y2, x2, z2 = source_pos[0], source_pos[1], source_pos[2]
    # compute translation of the source (loud speaker)
    # add small perturbation to have unique coordinate for trajectory generation purposes
    translation_y = -y1 + random.uniform(-0.001, 0.001)
    translation_x = -x1 + random.uniform(-0.001, 0.001)
    translation_z = z1 + random.uniform(-0.001, 0.001)
    # apply tranlation, note that the receiver (mic) remains at the same height
    receiver_centered = [0, 0, 0]
    source_translated = [x2 + translation_x, y2 + translation_y, translation_z - z2]
    return receiver_centered, source_translated


def create_single_sofa_file_arni(aud_fmt, arni_db_dir, sofa_db_dir, room="ARNI"):
    # Ensure the output directory exists
    if not os.path.exists(sofa_db_dir):
        os.makedirs(sofa_db_dir)

    # Gather all .sofa files in the source directory
    sofa_files = [file for file in os.listdir(arni_db_dir) if file.endswith(".sofa")]
    if not sofa_files:
        raise ValueError(f"Error: {arni_db_dir} contains no .sofa files")

    # Create the output file path
    filepath = os.path.join(sofa_db_dir, f"arni_{aud_fmt}.sofa")

    # Initialize containers for source and microphone positions, and RIRs
    source_positions, mic_positions, rirs = [], [], []

    # Process each sofa file
    for sofa_file in sorted(
        sofa_files, key=lambda x: get_absorption_level_arni(x)
    ):  # Sort by absorption level
        sofa_path = os.path.join(arni_db_dir, sofa_file)
        sofa = pysofa.SOFAFile(sofa_path, "r")

        if not sofa.isValid():
            print("Error: the file is invalid")
            break

        # Extract data from the SOFA object
        source_position = sofa.getVariableValue("SourcePosition")
        listener_position = sofa.getVariableValue("ListenerPosition")
        rir_data = sofa.getDataIR()

        # Assuming a fixed number of measurements to simplify
        num_measurements = 21  # Number of measurements to consider

        # Loop through each measurement
        for i in range(num_measurements):
            ir_data = rir_data[i, :]
            ir_data_resampled = librosa.resample(ir_data, orig_sr=48000, target_sr=FS)

            # Append data depending on the audio format
            if aud_fmt == "mic":
                rirs.append(
                    ir_data_resampled[__TETRA_CHANS_IN_EM32__, :]
                )  # Specific channels for 'mic' format
            else:  # 'foa' format
                rirs.append(ir_data_resampled[:4])

            # Compute the centered and translated positions
            mic_centered, src_translated = center_and_translate_arni(
                listener_position[i], source_position[i]
            )
            mic_positions.append(mic_centered)
            source_positions.append(src_translated)

    # Convert lists to numpy arrays
    rirs = np.array(rirs)
    mic_positions = np.array(mic_positions)
    source_positions = np.array(source_positions)

    # Create .sofa file
    sofa_utils.create_srir_sofa(
        filepath,
        rirs,
        source_positions,
        mic_positions,
        room_name=room,
        listener_name=aud_fmt,
        sr=FS,
        comment=f"SOFA conversion of room {room}",
    )


def prepare_arni(path_raw, path_sofa, formats=["mic", "foa"]):
    # generate sofa files
    sofa_db_dir = path_sofa
    for aud_fmt in formats:
        if aud_fmt == "mic":
            arni_db_dir = f"{path_raw}/6dof_SRIRs_eigenmike_raw"
        elif aud_fmt == "foa":
            arni_db_dir = f"{path_raw}/6dof_SRIRs_eigenmike_SH"
        print(f"Starting .sofa creation for {aud_fmt} format.")
        create_single_sofa_file_arni(aud_fmt, arni_db_dir, sofa_db_dir, ARNI_DB_NAME)
        print(f"Finished .sofa creation for {aud_fmt} format.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare RIR datasets.")
    parser.add_argument(
        "--path",
        default="datasets/rir_datasets",
        help="Path to store and process the dataset.",
    )
    args = parser.parse_args()
    source_path, sofa_path = Path(args.path) / "source_data", Path(args.path) / "spatialscaper_RIRs"
    [os.makedirs(p, exist_ok=True) for p in (source_path, sofa_path)]
    
    # # METU
    # download_and_extract_remotes(METU_REMOTES, dest_path)
    # prepare_metu(source_path, sofa_path)

    # ## TAU
    # download_tau(dest_path)
    # prepare_tau(source_path, sofa_path)

    # # ARNI
    # download_and_extract(ARNI_URL_MIC, Path(args.path) / "source_data")
    # download_and_extract(ARNI_URL_FOA, Path(args.path) / "source_data")
    # prepare_arni(source_path, sofa_path)

    # MOTUS
    download_and_extract_remotes(MOTUS_REMOTES, dest_path)
    prepare_motus(source_path, sofa_path) 
    