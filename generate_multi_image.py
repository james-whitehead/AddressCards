r""" generate_multi_image.py

Generates some postcards about bin collection data using data from the Local Land and Property Gazetteer (LLPG).

## How to run

The program doesn't take any command line arguments, so it can be run however you would run a Python 3 script:

If Python 3 is the only environment installed:

* `python .\generate_multi_image.py`

If Python 2 is installed as well and you're using some variant of the Windows launcher:

* `python3 .\generate_multi_image.py`

* `py -3 .\generate_multi_image.py`

## How it works

1. get_uprns() returns a list of Unique Property Reference Numbers (UPRNs) used to identify each property that bins are collected from.
2. The list of UPRNs is split into sublists of four UPRNs each, because the generated postcards are four A5 cards in a grid on an A3 (or SRA3) sheet.
3. For each single UPRN in a list of four, a Calendar object and an Address object are created. A Calendar object contains the data for when the bins are collected, and the Address object contains the address data for the property.
4. A CalendarImage object and AddressImage object are created using the Calendar and Address objects. The attributes calendar_image and address_image are PIL.Image types from the Pillow imaging library. The attributes calendar and address are the parent Calendar and Address objects. This creates a list of four CalendarImages and four AddressImages.
5. The eight images are arranged in a grid into a CalendarSide and an AddressSide themselves being PIL.Image tyoes, which are saved as two separate JPEG images.
6. The images are converted into PDFs and merged together into groups of 150.

## Notes for the future

Assuming the data follows the same format as these SQL queries, this program should be very extensible for use in the future. There may be a few caveats and important things to note, however:

* This was written in Python 3.6.4 using Pillow 5.0.0. It won't work on Python 2, but should be simple enough to work on any future versions.
* The centring of text on the bins is _really_ awkward. Pillow has no concept of centre-aligning text, so each string has to be split into separate lines using textwrap.wrap(), and the width of each line needs to be calculated so the text can be placed relative to each other so it's 'centred'. The string splits nicely into lines of 7 characters, but if the string changes in the future, this value might have to change.
* The program takes about five hours to process 5000 UPRNs and doesn't handle crashes gracefully. Crashes can be caused by unexpected NULLs in the SQL results or by the SQL server itself going down, as well as anything happening locally on the machine running it. Leave plenty of time spare to produce things.
* The template images may need to be converted from the CMYK colour space to RGB if the colours look too bright. A good place to do this is here https://www.cmyk2rgb.com/
* This could be a lot more nicely object-oriented, but as it stands, CalendarSide and AddressSide are annoyingly separate. Any changes that need to be made to both sides will need to be made in both sides.
* This doesn't generate different images for properties that have their recycling bins and glass recycling bins collected on different days. This may be needed for a later batch. Some of the very basic templates are there, but don't actually do anything.
* Powershell sometimes gets stuck while running it. I don't know why, and it's not great, so you'll have to keep an eye on it and tap a key to get it running again.
"""

import json
import textwrap
import os
import gc
from PIL import Image, ImageDraw, ImageFont, ImageOps
import pyodbc

class ConnectionString:
    """ Represents a pyodbc connection string
    """

    def __init__(self):
        """ Reads the attributes from a config file
        """
        with open('.config') as config_file:
            config = json.load(config_file)
            self.driver = config['driver']
            self.server = config['server']
            self.database = config['database']
            self.uid = config['uid']
            self.pwd = config['pwd']


class Calendar:
    """ Represents a set of days on which particular bins are collected.
    """

    def __init__(self, connection, uprn):
        """ Maps each day to a date and calls the methods to create the
        calendar
        """
        self.dates = {
            'Monday': 0,
            'Tuesday': 1,
            'Wednesday': 2,
            'Thursday': 3,
            'Friday': 4}
        self.connection = connection
        self.uprn = uprn
        self.get_calendar_data()
        self.format_calendar_strings()

    def get_calendar_data(self):
        """ Queries the database using to get the calendar data
        """
        with open('./cal_query.sql', 'r') as query_file:
            query = query_file.read()
            cursor = self.connection.cursor()
            cursor.execute(query, self.uprn)
            row = cursor.fetchone()
            self.black_bin_day = row.REFDay
            self.black_bin_week = row.REFWeek
            self.recycling_bin_day = row.RECYDay
            self.recycling_bin_week = row.RECYWeek
            self.recycling_box_day = row.RECYDay
            self.recycling_box_week = row.RECYWeek
            self.green_bin_day = row.GWDay
            self.green_bin_week = row.GWWeek
            cursor.close()

    def format_calendar_strings(self):
        """ Formats the calendar data to match the design of the card
        """
        self.black_bin_str = '{}   from   {} June 2018'.format(
            self.black_bin_day,
            str((self.black_bin_week * 7) + self.dates[self.black_bin_day] + 4))
        self.recycling_bin_str = '{}   from   {} June 2018'.format(
            self.recycling_bin_day,
            str((self.recycling_bin_week * 7) + self.dates[self.recycling_bin_day] + 4))
        if self.recycling_box_day == self.recycling_bin_day:
            self.recycling_box_str = ''
        else:
            self.recycling_box_str = '{}   from   {} June 2018'.format(
                self.recycling_box_day,
                str((self.recycling_box_week * 7) + self.dates[self.recycling_bin_day] + 4))
        if self.green_bin_day is None:
            self.green_bin_str = 'Not collected'
        else:
            self.green_bin_str = '{}   from   {} June 2018'.format(
                self.green_bin_day,
                str((self.green_bin_week * 7) + self.dates[self.green_bin_day] + 4))


class CalendarImage:
    """ Represents a single image of some bins with some calendar data on top
    """

    def __init__(self, calendar, index):
        """ Sets some values used to generate the correct image
        """
        self.calendar = calendar
        if index == 1:
            self.index = 2
        elif index == 2:
            self.index = 1
        elif index == 3:
            self.index = 4
        elif index == 4:
            self.index = 3
        self.calendar_font = ImageFont.truetype(
            'futura bold condensed italic bt.ttf', 59)
        self.index_font = ImageFont.truetype('consola.ttf', 40)
        self.load_calendar_image()
        self.image = self.build_calendar_image()

    def load_calendar_image(self):
        """ Loads the correct image based on image type
        """
        # If the recycling box and bins are collected simultaneously
        if self.calendar.recycling_box_str == '':
            self.image_type = 'SAME_COLLECTION'
            self.calendar_image = Image.open(
                './in/postcard-back-same-dates.jpg').convert('RGB')
            self.calendar_image.load()

    def build_calendar_image(self):
        """ Builds the correct image using the background and calendar data
        """
        if self.image_type == 'SAME_COLLECTION':
            black_bin_str = wrap_text(calendar.black_bin_str, 7)
            black_bin_text = create_text_box(
                black_bin_str,
                # Width, height and rotation of the text box
                300, 450, 4,
                self.calendar_font,
                255,
                False)
            paste_text_box(
                self.calendar_image,
                black_bin_text,
                # X and Y coordinate of the text box
                380, 710,
                (255, 255, 255),
                (255, 255, 255))
            recycling_bin_str = wrap_text(calendar.recycling_bin_str, 7)
            recycling_bin_text = create_text_box(
                recycling_bin_str,
                300, 450, 4,
                self.calendar_font,
                255,
                False)
            paste_text_box(
                self.calendar_image,
                recycling_bin_text,
                1070, 710,
                (255, 255, 255),
                (255, 255, 255))
            recycling_box_str = wrap_text(calendar.recycling_box_str, 7)
            recycling_box_text = create_text_box(
                recycling_box_str,
                400, 250, 4,
                self.calendar_font,
                255,
                False)
            paste_text_box(
                self.calendar_image,
                recycling_box_text,
                935, 710,
                (255, 255, 255),
                (255, 255, 255))
            green_bin_str = wrap_text(calendar.green_bin_str, 7)
            green_bin_text = create_text_box(
                green_bin_str,
                300, 450, 4,
                self.calendar_font,
                255,
                False)
            paste_text_box(
                self.calendar_image,
                green_bin_text,
                1975, 710,
                (255, 255, 255),
                (255, 255, 255))
            # Keeps track of corresponding addresses and calendars
            number = create_text_box(
                str(self.index),
                100, 100, 0,
                self.index_font,
                255,
                True)
            paste_text_box(
                self.calendar_image,
                number,
                0, 0,
                (0, 0, 0),
                (0, 0, 0))
            uprn = create_text_box(
                self.calendar.uprn,
                1000, 100, 0,
                self.index_font,
                255,
                True)
            paste_text_box(
                self.calendar_image,
                uprn,
                750, 0,
                (0, 0, 0),
                (0, 0, 0))
        if self.image_type == 'DIFFERENT_COLLECTION':
            print('TODO: handle different image collection')
        return self.calendar_image


class CalendarSide:
    """ Represents a collection of four CalendarImage objects pasted on a
    blank image
    """

    def __init__(self, calendar_image_list):
        """ Defines the positions for the calendar images
        """
        self.calendar_image_list = calendar_image_list
        # X and Y offsets for top-left, top-right, bottom-left, bottom-right
        self.positions = [(82, 47), (2657, 47), (82, 1890), (2657, 1890)]
        self.calendar_side_image = Image.open(
            './in/blank_sra3.jpg').convert('RGB')
        self.calendar_side_image.load()
        self.build_calendar_side()
        uprns = []
        for calendar_image in self.calendar_image_list:
            uprns.append(calendar_image.calendar.uprn)
        # Reverts the UPRNs back to normal so filenames are the same
        unflipped_uprns = [uprns[2], uprns[3], uprns[0], uprns[1], 'cal']
        self.new_file = save_image(
            '-'.join(unflipped_uprns), self.calendar_side_image)

    def build_calendar_side(self):
        """ Pastes each CalendarImage at the correct position on the blank
        page to create a 4x4 grid
        """

        for position, calendar_image in enumerate(self.calendar_image_list):
            paste_image(
                self.calendar_side_image,
                calendar_image.image,
                self.positions[position][0],
                self.positions[position][1])


class Address:
    """ Represents a Royal Mail standard address of a property
    """

    def __init__(self, connection, uprn):
        """ Calls the methods to create an address
        """
        self.connection = connection
        self.uprn = uprn
        self.get_address_data()
        self.format_address_string()

    def get_address_data(self):
        """ Queries the database to get the address data
        """
        with open('./cal_query.sql', 'r') as query_file:
            query = query_file.read()
            cursor = self.connection.cursor()
            cursor.execute(query, self.uprn)
            row = cursor.fetchone()
            self.address_block = row.addressBlock

    def format_address_string(self):
        """ Formats the address data to match the design of the card
        """
        self.address_block = self.address_block.replace('<br>', '\n')


class AddressImage:
    """ Represents a single image of a postal address
    """

    def __init__(self, address, index):
        """ Sets some values used to generate the correct images
        """
        self.address = address
        self.index = index
        self.address_font = ImageFont.truetype('arial.ttf', 45)
        self.index_font = ImageFont.truetype('consola.ttf', 40)
        self.address_image = Image.open(
            './in/postcard-front.jpg').convert('RGB')

        self.address_image.load()
        self.build_address_image()

    def build_address_image(self):
        """ Builds the correct image using the background and address data
        """
        text_box = create_text_box(
            self.address.address_block,
            1900, 850, 0,
            self.address_font,
            255,
            True)
        paste_text_box(
            self.address_image,
            text_box,
            500, 700,
            (0, 0, 0),
            (0, 0, 0))
        number = create_text_box(
            str(self.index),
            100, 100, 0,
            self.index_font,
            255,
            True)
        paste_text_box(
            self.address_image,
            number,
            0, 0,
            (0, 0, 0),
            (0, 0, 0))
        uprn = create_text_box(
            self.address.uprn,
            1000, 100, 0,
            self.index_font,
            255,
            True)
        paste_text_box(
            self.address_image,
            uprn,
            750, 0,
            (0, 0, 0),
            (0, 0, 0))


class AddressSide:
    """ Represents a collection of four AddressSide objects pasted on a blank
    image
    """

    def __init__(self, address_image_list):
        """ Defines the positions for the calendar images
        """
        self.address_image_list = address_image_list
        # X and y offsets for top-left, top-right, bottom-left, bottom-right
        self.positions = [(82, 47), (2657, 47), (82, 1890), (2657, 1890)]
        self.address_side_image = Image.open(
            './in/blank_sra3.jpg').convert('RGB')
        self.address_side_image.load()
        self.build_address_side()
        filename = ['addr']
        for address_image in self.address_image_list:
            filename = [address_image.address.uprn] + filename
        self.new_file = save_image('-'.join(filename), self.address_side_image)

    def build_address_side(self):
        """ Pastes each AddressImage at the correct position on the blank page
        to create a 4x4 grid
        """
        for position, address_image in enumerate(self.address_image_list):
            paste_image(
                self.address_side_image,
                address_image.address_image,
                self.positions[position][0],
                self.positions[position][1])


def get_uprns(connection):
    """ Gets a list of 1000 UPRNs from the database and splits them into a
    list of lists, each sublist containing 4 elements.
    """
    uprns = []
    with open('./uprn_query.sql', 'r') as query_file:
        query = query_file.read()
        cursor = connection.cursor()
        cursor.execute(query)
        uprn_col = cursor.fetchall()
        for row in uprn_col:
            uprns.append(row[0])
        return [uprns[i:i + 4] for i in range(0, len(uprns), 4)]

def wrap_text(string, width):
    """ Wraps a given string on to multiple lines to fit the image
    """
    return textwrap.wrap(
        string,
        width=width,
        replace_whitespace=False,
        break_long_words=False)

def create_text_box(string, width, height, rotation, font, fill, multiline):
    """ Creates a text box to hold some string data
    """
    text_box = Image.new('L', (width, height))
    text_box_draw = ImageDraw.Draw(text_box)
    # If the string doesn't have built-in linebreaks (i.e. calendar string)
    if not multiline:
        padding = 10
        current_height = 50
        for line in string:
            line_width, line_height = text_box_draw.textsize(line, font=font)
            # Writes the text to the box so it's centre aligned
            text_box_draw.text(
                ((width - line_width) / 2, current_height),
                line,
                font=font,
                fill=fill)
            current_height += line_height + padding
    else:
        text_box_draw.multiline_text(
            (0, 0), string, font=font, fill=fill, spacing=20)
    return text_box.rotate(rotation, resample=Image.BICUBIC, expand=True)

def paste_text_box(base_image, text_box, x_coord, y_coord, rgb_black, rgb_white):
    """ Pastes a text box on to an image, given a set of coordinates
    """
    base_image.paste(
        ImageOps.colorize(
            text_box,
            rgb_black,
            rgb_white),
        (x_coord, y_coord),
        text_box)

def paste_image(base_image, image_to_paste, x_coord, y_coord):
    """ Pasts an image on to another image, given a set of coordinates
    """
    base_image.paste(image_to_paste, (x_coord, y_coord))

def save_image(filename, image):
    """ Saves an image to file
    """
    out_path = './out/{}.jpg'.format(filename)
    image.save(
        out_path, quality=95, dpi=(300,300), optimize=True)
    return out_path

def convert_to_pdf():
    """ Converts all the images in the output folder into a single PDF with
    each image on one page
    """
    paths = sorted([os.path.join('./out', f) for f in next(os.walk('./out'))[2]])
    # Splits paths into groups to avoid MemoryErrors
    paths = [paths[i:i + 150] for i in range(0, len(paths), 150)]
    list_count = 0
    img_count = 0
    for sublist in paths:
        loaded_images = []
        for image in sublist:
            if img_count % 150 == 0:
                first_image = Image.open(image)
            else:
                loaded_images.append(Image.open(image))
            img_count += 1
        list_count += 1
        path = './{}-output.pdf'.format(list_count)
        first_image.save(
            # Resolution is not a percentage, but the DPI values
            path, 'PDF', resolution=300, save_all=True,
            append_images=loaded_images)
        print('Saved {} images'.format(img_count))
        # Garbage collection to stop MemoryErrors
        del loaded_images
        gc.collect()

if __name__ == '__main__':
    pyodbc.pooling = False
    CONN_STRING = ConnectionString()
    CONN = pyodbc.connect(
        driver=CONN_STRING.driver,
        server=CONN_STRING.server,
        database=CONN_STRING.database,
        uid=CONN_STRING.uid,
        pwd=CONN_STRING.pwd)
    UPRN_LISTS = get_uprns(CONN)
    for index, uprn_list in enumerate(UPRN_LISTS, 1):
        calendar_images = []
        address_images = []
        # Order needs to be swapped around on the calendar side for printing
        swapped_list = [uprn_list[1], uprn_list[0], uprn_list[3], uprn_list[2]]
        for number, uprn in enumerate(uprn_list, 1):
            address = Address(CONN, uprn)
            address_image = AddressImage(address, number)
            address_images.append(address_image)
        for number, uprn in enumerate(swapped_list, 1):
            calendar = Calendar(CONN, uprn)
            calendar_image = CalendarImage(calendar, number)
            calendar_images.append(calendar_image)
        address_side = AddressSide(address_images)
        calendar_side = CalendarSide(calendar_images)
        print('{}: {}'.format(index, address_side.new_file))
        print('{}: {}'.format(index, calendar_side.new_file))
    convert_to_pdf()
    CONN.close()
