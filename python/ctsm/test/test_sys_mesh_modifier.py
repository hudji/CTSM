#!/usr/bin/env python3

"""System tests for mesh_mask_modifier"""

import os
import sys
import re
import subprocess

import unittest
import tempfile
import shutil

import xarray as xr

from ctsm.path_utils import path_to_ctsm_root
from ctsm import unit_testing
from ctsm.modify_mesh_mask.mesh_mask_modifier import mesh_mask_modifier

# Allow test names that pylint doesn't like; otherwise hard to make them
# readable
# pylint: disable=invalid-name


class TestSysMeshMaskModifier(unittest.TestCase):
    """System tests for mesh_mask_modifier"""

    def setUp(self):
        """
        Obtain path to the existing:
        - modify_template.cfg file
        - /testinputs directory and fsurdat_in, located in /testinputs
        Make /_tempdir for use by these tests.
        Obtain path and names for the files being created in /_tempdir:
        Generate mesh_mask_in.nc applying nco/esmf commands on fsurdat_in.
        Generate landmask.nc applying nco commands on fsurdat_in.
        """
        # Obtain various paths and make /_tempdir
        self._cfg_template_path = os.path.join(
            path_to_ctsm_root(), "tools/modify_mesh_mask/modify_template.cfg"
        )
        testinputs_path = os.path.join(path_to_ctsm_root(), "python/ctsm/test/testinputs")
        fsurdat_in = os.path.join(
            testinputs_path,
            "surfdata_5x5_amazon_16pfts_Irrig_CMIP6_simyr2000_c171214.nc",
        )
        self._tempdir = tempfile.mkdtemp()
        self._cfg_file_path = os.path.join(self._tempdir, "modify_mesh_mask.cfg")
        self._mesh_mask_in = os.path.join(self._tempdir, "mesh_mask_in.nc")
        self._mesh_mask_out = os.path.join(self._tempdir, "mesh_mask_out.nc")
        self._landmask_file = os.path.join(self._tempdir, "landmask.nc")
        scrip_file = os.path.join(self._tempdir, "scrip.nc")
        metadata_file = os.path.join(self._tempdir, "metadata.nc")

        # Generate mesh_mask_in from fsurdat_in
        ncks_cmd = f'ncks --rgr infer --rgr scrip={scrip_file} {fsurdat_in} {metadata_file}'
        try:
            subprocess.check_call(ncks_cmd, shell=True)
        except subprocess.CalledProcessError as e:
            sys.exit(f'{e} ERROR using ncks to generate {scrip_file} from {fsurdat_in}')
        # TODO How to make the esmf command generic?
        # TODO How to write the PET0 file in /tempdir or suppress entirely?
        esmf_cmd = f'/glade/u/apps/ch/opt/esmf-netcdf/8.0.0/intel/19.0.5/bin/bing/Linux.intel.64.mpiuni.default/ESMF_Scrip2Unstruct {scrip_file} {self._mesh_mask_in} 0'
        try:
            subprocess.check_call(esmf_cmd, shell=True)
        except subprocess.CalledProcessError as e:
            sys.exit(f'{e} ERROR using esmf to generate {self._mesh_mask_in} from scrip.nc')

        # Generate landmask_file from fsurdat_in
        self._lat_dimname = 'lsmlat'  # same as in fsurdat_in
        self._lon_dimname = 'lsmlon'  # same as in fsurdat_in
        self._lat_varname = 'LATIXY'  # same as in fsurdat_in
        self._lon_varname = 'LONGXY'  # same as in fsurdat_in
        fsurdat_in_data = xr.open_dataset(fsurdat_in)
        assert self._lat_varname in fsurdat_in_data.variables
        assert self._lon_varname in fsurdat_in_data.variables
        assert self._lat_dimname in fsurdat_in_data.dims
        assert self._lon_dimname in fsurdat_in_data.dims

        ncap2_cmd = f"ncap2 -A -v -s 'mod_lnd_props=PFTDATA_MASK' -A -v -s 'landmask=PFTDATA_MASK' -A -v -s {self._lat_varname}={self._lat_varname} -A -v -s {self._lon_varname}={self._lon_varname} {fsurdat_in} {self._landmask_file}"
        try:
            subprocess.check_call(ncap2_cmd, shell=True)
        except subprocess.CalledProcessError as e:
            sys.exit(f'{e} ERROR using ncap2 to generate {self._landmask_file} from {fsurdat_in}')

    def tearDown(self):
        """
        Remove temporary directory
        """
        shutil.rmtree(self._tempdir, ignore_errors=True)

    def test_allInfo(self):
        """
        This test specifies all the information that one may specify
        Create .cfg file, run the tool, compare mesh_mask_in to mesh_mask_out
        """

        self._create_config_file()

        # run the mesh_mask_modifier tool
        mesh_mask_modifier(self._cfg_file_path)
        # the critical piece of this test is that the above command
        # doesn't generate errors; however, we also do some assertions below

        # Error checks
        mesh_mask_in_data = xr.open_dataset(self._mesh_mask_in)
        mesh_mask_out_data = xr.open_dataset(self._mesh_mask_out)

        center_coords_in = mesh_mask_in_data.centerCoords
        center_coords_out = mesh_mask_out_data.centerCoords
        self.assertTrue(center_coords_out.equals(center_coords_in))
        # the Mask variable will now equal zeros, not ones
        element_mask_in = mesh_mask_in_data.elementMask
        element_mask_out = mesh_mask_out_data.elementMask
        self.assertTrue(element_mask_out.equals(element_mask_in-1))

    def _create_config_file(self):
        """
        Open the new and the template .cfg files
        Loop line by line through the template .cfg file
        When string matches, replace that line's content
        """
        with open(self._cfg_file_path, "w", encoding="utf-8") as cfg_out:
            with open(self._cfg_template_path, "r", encoding="utf-8") as cfg_in:
                for line in cfg_in:
                    if re.match(r" *mesh_mask_in *=", line):
                        line = f"mesh_mask_in = {self._mesh_mask_in}"
                    elif re.match(r" *mesh_mask_out *=", line):
                        line = f"mesh_mask_out = {self._mesh_mask_out}"
                    elif re.match(r" *landmask_file *=", line):
                        line = f"landmask_file = {self._landmask_file}"
                    elif re.match(r" *lat_dimname *=", line):
                        line = f"\nlat_dimname = {self._lat_dimname}"
                    elif re.match(r" *lon_dimname *=", line):
                        line = f"\nlon_dimname = {self._lon_dimname}"
                    elif re.match(r" *lat_varname *=", line):
                        line = f"\nlat_varname = {self._lat_varname}"
                    elif re.match(r" *lon_varname *=", line):
                        line = f"\nlon_varname = {self._lon_varname}"
                    cfg_out.write(line)


if __name__ == "__main__":
    unit_testing.setup_for_tests()
    unittest.main()
