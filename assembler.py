import os
import re
from PIL import Image
import json
import tempfile
import shutil
import argparse
import time


class PartColorsNotFound(Exception):
    pass


def empty_directory(directory):
    filelist = [f for f in os.listdir(directory) if f.endswith(".png")]
    for f in filelist:
        os.remove(os.path.join(directory, f))


def ensure_directory(directory):
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory, ignore_errors=True)
        os.makedirs(directory)
    except:
        pass


class Assembler(object):

    TEMP_DIR = os.path.join(tempfile.gettempdir(), 'PngAssembler')

    rgx_partname = re.compile(r'^\d+?(.+)\.png')
    rgx_maskoptions = re.compile(r'(.+)\.\d+\.png')
    rgx_dotpart = re.compile(r'\..+$')
    rgx_prefix_num = re.compile(r'\d+?(.+)')
    rgx_tatoo = re.compile(r'\d+tat$', re.I)

    def __init__(self, mask_directory, sav_file=None):

        print('Creating temporary @ directory {}'.format(self.TEMP_DIR))
        ensure_directory(self.TEMP_DIR)

        self.mask_directory = mask_directory
        self.data_file = sav_file

        print('reading json data file...')
        with open(self.data_file, 'rt') as fp:
            json_data = json.loads(fp.read())
            json_data = json_data[0]
            # for item in json_data:
            if json_data['partColors']:
                self.part_colors = json_data['partColors']
            if json_data['activeTabs'] and len(json_data['activeTabs'].keys()) > 2:
                self.active_tabs = json_data['activeTabs']

            if not self.part_colors or not self.active_tabs:
                print('active tabs/part colors missing from json data')
                return

            if not self.part_colors:
                raise PartColorsNotFound()

        #self.masks = list(self._get_masks())
        self.masks = dict({mask_name: (mask_path, mask_name, mask_bytes)
                           for mask_path, mask_name, mask_bytes in self._get_masks()})

    def _locate_data_file(self):
        files = os.listdir(self.mask_directory)
        for f in files:
            root, ext = os.path.splitext(f)
            if '.sav' in ext.lower():
                return os.path.abspath(os.path.join(self.mask_directory, f))

        raise FileNotFoundError()

    def _get_part_name(self, filename):

        match = self.rgx_partname.search(filename)
        #match = self.rgx_partname.search(filename.replace('_', ''))
        if match:
            partname = self.rgx_dotpart.sub('', match.group(0).strip())
            return partname

    def _get_masks(self):

        for root, dirs, files in os.walk(self.mask_directory):
            for f in files:
                fn, ext = os.path.splitext(f)
                if not 'png' in ext.lower():
                    continue

                yield (
                    os.path.join(root, f),
                    self._get_part_name(f),
                    Image.open(
                        os.path.join(root, f)).convert('L')
                )

    def __is_tatoo(self, mask_name):
        result = self.rgx_tatoo.search(mask_name)
        if result:
            return True

        return False

    def __is_pat(self, pat_name):
        re_pat = re.compile(r'Pat\d*$')
        return re_pat.search(pat_name) != None

    def _apply_color_to_pngs(self):

        print('Emptying temporary files: {}'.format(self.TEMP_DIR))
        print('Applying colors to masks using data file: {}'.format(self.data_file))
        empty_directory(self.TEMP_DIR)
        for mask in sorted([k for k in self.masks.keys() if k]):
            mask_path, mask_name, mask_bytes = self.masks[mask]

            if self.__is_pat(mask_name):
                continue

            if not mask_name:
                print('skipping unknown mask file (mask name is None)')
                continue

            if self.__is_tatoo(mask_name):
                if self.active_tabs.get(mask_name, 0) == 0:
                    continue

            if 'gloss' in mask_name.lower():
                # color = {
                #     "r": 1,
                #     "g": 1,
                #     "b": 1,
                # }
                continue
            else:
                try:
                    color = self.part_colors[mask_name]
                except KeyError:
                    print(
                        'No color info found for part <{}>. I will be using WHITE.'.format(mask_name))
                    color = {
                        "r": 1,
                        "g": 1,
                        "b": 1,
                    }

            if not 'r' in color or not 'g' in color or not 'b' in color:
                color = {
                    "r": 1,
                    "g": 1,
                    "b": 1,
                }

            red = int(color['r'] * 255)
            green = int(color['g'] * 255)
            blue = int(color['b'] * 255)

            im = Image.new('RGB', mask_bytes.size, (red, green, blue))
            new = Image.new('RGB', mask_bytes.size)
            new.paste(im, None, mask_bytes)
            head, tail = os.path.split(mask_path)

            new.save(os.path.join(self.TEMP_DIR, tail))

        print('Done applying colors')

    def _locate_mask(self, part_name):
        return self.masks[part_name]

    def _get_current_size(self):
        key = next(iter(self.masks))
        mpath, mname, mbytes = self.masks[key]
        return mbytes.size

    def _merge(self):
        print('Merging all image part from : {} to a single PNG.'.format(self.TEMP_DIR))
        current_image = Image.new('RGB', self._get_current_size())

        # gloss_layer_path = None
        # gloss_layer_mask_name = None

        for root, dirs, files in os.walk(self.TEMP_DIR):
            for f in sorted(files):
                part_name = self._get_part_name(f)
                layer_path = os.path.join(root, f)

                if 'gloss' in part_name.lower():
                    # gloss_layer_path = layer_path
                    # gloss_layer_mask_name = self._get_part_name(f)
                    continue

                print("Merging {}".format(part_name))
                im = Image.open(layer_path)
                mask_path, mask_name, mask_bytes = self.masks[part_name]
                current_image.paste(im, None, mask_bytes)

        # if gloss_layer_path and gloss_layer_mask_name:
        #     print('Applying gloss: ' + gloss_layer_path)
        #     white = Image.new('L', self._get_current_size(), 255)
        #     gloss_mask_path, gloss_mask_name,  gloss_mask_bytes = self.masks[
        #         gloss_layer_mask_name]

        #     #gloss = Image.open(gloss_layer_path)
        #     current_image.paste(white, None, gloss_mask_bytes)
        # else:
        #     if not gloss_layer_path:
        #         print('No Gloss part found')

        #     if not gloss_layer_mask_name:
        #         print('No Gloss mask part found')

        #fname, ext = os.path.splitext(self.data_file)
        #output = os.path.join(fname + '.png')
        #print('Saving final output png to: {}'.format(output))
        # current_image.save(output)
        return current_image

    def __remove_prefix(self, text):
        rslt = self.rgx_prefix_num.search(text)
        if rslt:
            return rslt.group(1)
        return text

    def _find_maskoption(self, opt_name, opt_value):
        re_pat = re.compile(r'Pat\d*$')

        if not re_pat.search(opt_name) or opt_value == 0:
            return

        files = os.listdir(self.mask_directory)
        for f in files:
            option_filename = 'Pat{}.png'.format(opt_value)
            # if option_filename == f:
            if f == option_filename:
                return Image.open(os.path.join(self.mask_directory, f)).convert('L')

            option_filename = '{}_V{}.png'.format(
                self.__remove_prefix(opt_name), opt_value)
            # if option_filename == f:
            if f == option_filename:
                return Image.open(os.path.join(self.mask_directory, f)).convert('L')

    def _apply_mask_options(self, current_image):

        if not self.active_tabs:
            print('Unable to apply mask options. No values for activeTabs found.')
            return current_image

        print('Applying Mask Options')
        for option_name in self.active_tabs.keys():
            option_value = self.active_tabs.get(option_name, 0)
            if option_value == 0:
                continue

            mask_option_bytes = self._find_maskoption(
                option_name, option_value)

            if not mask_option_bytes:
                print('No mask found for {}.{}.png'.format(
                    option_name, option_value))
                continue

            if not option_name in self.part_colors:
                print('No color information found for {}.{}.png'.format(
                    option_name, option_value))
                continue

            print('Mask option found for {}.{}.png'.format(
                option_name, option_value))
            print('Applying...')
            red = int(self.part_colors[option_name]['r'] * 255)
            green = int(self.part_colors[option_name]['g'] * 255)
            blue = int(self.part_colors[option_name]['b'] * 255)
            im = Image.new('RGB', mask_option_bytes.size, (red, green, blue))
            current_image.paste(im, None, mask_option_bytes)

        return current_image

    def _apply_gloss(self, current_image):
        gloss_layer_mask_name, gloss_layer_path = (None, None)

        print('Trying to look for a gloss file')
        for root, dirs, files in os.walk(self.mask_directory):
            for f in files:

                if not f.endswith('.png'):
                    continue

                part_name = self._get_part_name(f)
                layer_path = os.path.join(root, f)

                if not part_name:
                    continue

                if 'gloss' in part_name.lower():
                    print('Gloss image found!')
                    gloss_layer_path = layer_path
                    gloss_layer_mask_name = self._get_part_name(f)
                    break
            break

        if gloss_layer_path and gloss_layer_mask_name:
            print('Applying gloss: ' + gloss_layer_path)
            white = Image.new('L', self._get_current_size(), 255)
            gloss_mask_path, gloss_mask_name, gloss_mask_bytes = self.masks[
                gloss_layer_mask_name]

            #gloss = Image.open(gloss_layer_path)
            current_image.paste(white, None, gloss_mask_bytes)
        else:
            if not gloss_layer_path:
                print('No Gloss part found')

            if not gloss_layer_mask_name:
                print('No Gloss mask part found')

        return current_image

    def assemble(self):
        print('PNG assebling started.')
        print('Using masks directory: {}'.format(self.mask_directory))
        print('Using temporary directory: {}'.format(
            os.path.abspath(self.TEMP_DIR)))

        self._apply_color_to_pngs()

        current_image = self._merge()
        current_image = self._apply_mask_options(current_image)
        current_image = self._apply_gloss(current_image)

        fname, ext = os.path.splitext(self.data_file)
        output = os.path.join(fname + '.png')
        print('Saving final output png to: {}'.format(output))
        current_image.save(output)
        return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('savfile')
    parser.add_argument('mask')
    options = parser.parse_args()

    print(
        f'Processing {options.savfile} using mask directory {options.mask}')
    assembler = Assembler(options.mask, sav_file=options.savfile)
    tick = time.perf_counter()
    assembler.assemble()
    print(
        f"It took a total of {(time.perf_counter() - tick)} seconds to generate Color texture.")
