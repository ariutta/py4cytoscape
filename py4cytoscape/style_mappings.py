# -*- coding: utf-8 -*-

"""Functions for defining MAPPINGS between table column values and visual properties, organized into sections:

I. General functions for creating and applying mappings for node, edge and network properties
II. Specific functions for defining particular node, edge and network properties

License:
    Copyright 2020 The Cytoscape Consortium

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
    and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial portions
    of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
    WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
    OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

# External library imports
import sys
import time

# Internal module imports
from . import networks
from . import commands
from . import styles
from . import style_defaults

# Internal module convenience imports
from .exceptions import CyError
from .py4cytoscape_utils import *
from .py4cytoscape_logger import cy_log
from .py4cytoscape_tuning import MODEL_PROPAGATION_SECS


# ==============================================================================
# I. General Functions
# ------------------------------------------------------------------------------

# TODO: R seems to allow table_column_value, visual_prop_values to be unspecified ... Python does this with optional parameters
@cy_log
def map_visual_property(visual_prop, table_column, mapping_type, table_column_values=[],
                        visual_prop_values=[], network=None, base_url=DEFAULT_BASE_URL):
    """Creates a mapping between an attribute and a visual property.

    Generates the appropriate data structure for the "mapping" parameter in ``update_style_mapping``.

    The paired list of values must be of the same length or mapping will fail. For gradient mapping,
    you may include two additional ``visual_prop_values`` in the first and last positions to map respectively
    to values less than and greater than those specified in ``table_column_values``. Mapping will also fail if the
    data type of ``table_column_values`` does not match that of the existing ``table_column``. Note that all imported
    numeric data are stored as Integers or Doubles in Cytosacpe tables; and character or mixed data are
    stored as Strings.

    Args:
        visual_prop (str): name of visual property to map
        table_column (str): name of table column to map
        mapping_type (str): continuous, discrete or passthrough (c,d,p)
        table_column_values (list): list of values paired with ``visual_prop_values``; skip for passthrough mapping
        visual_prop_values (list): list of values paired with ``table_column_values``; skip for passthrough mapping
        network (SUID or str or None): Name or SUID of a network. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        dict: {'mappingType': type of mapping, 'mappingColumn': column to map, 'mappingColumnType': column data type, 'visualProperty': name of property, cargo}

    Raises:
        CyError: if network name or SUID doesn't exist
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> map_visual_property('node fill color', 'gal1RGexp', 'c', [-2.426, 0.0, 2.058], ['#0066CC', '#FFFFFF','#FFFF00'])
        {'mappingType': 'continuous', 'mappingColumn': 'gal1RGexp', 'mappingColumnType': 'Double', 'visualProperty': 'NODE_FILL_COLOR', 'points': [{'value': -2.426, 'lesser': '#0066CC', 'equal': '#0066CC', 'greater': '#0066CC'}, {'value': 0.0, 'lesser': '#FFFFFF', 'equal': '#FFFFFF', 'greater': '#FFFFFF'}, {'value': 2.058, 'lesser': '#FFFF00', 'equal': '#FFFF00', 'greater': '#FFFF00'}]}
        >>> map_visual_property('node shape', 'degree.layout', 'd', [1, 2], ['ellipse', 'rectangle'])
        {'mappingType': 'discrete', 'mappingColumn': 'degree.layout', 'mappingColumnType': 'Integer', 'visualProperty': 'NODE_SHAPE', 'map': [{'key': 1, 'value': 'ellipse'}, {'key': 2, 'value': 'rectangle'}]}
        >>> map_visual_property('node label', 'COMMON', 'p')
        {'mappingType': 'passthrough', 'mappingColumn': 'COMMON', 'mappingColumnType': 'String', 'visualProperty': 'NODE_LABEL'}

    Note:
        For the return value, ``mapping type`` can be 'continuous', 'discrete' or 'passthrough'. For the
        ``mappingColumn``, the name of the column. For the ``mappingColumnType``, the Cytoscape data type (Double,
        Integer, String, Boolean). For the ``visualProperty``, the canonical name of the visual property. The ``cargo``
        depends on the ``mapping type``. For 'continuous', it's a list of way points as 'points': [waypoint, waypoint, ...]
        where a waypoint is {'value': a Double, 'lesser': a color, 'equal': a color, 'greater': a color}. For 'discrete',
        it's a list of mappings as 'map': [key-value, key-value, ...] where a key-value is {'key': column data value,
        'value': value appropriate for ``visualProperty``}.

    See Also:
        :meth:`update_style_mapping`, :meth:`get_visual_property_names`
    """
    MAPPING_TYPES = {'c': 'continuous', 'd': 'discrete', 'p': 'passthrough'}
    PROPERTY_NAMES = {'EDGE_COLOR': 'EDGE_UNSELECTED_PAINT', 'EDGE_THICKNESS': 'EDGE_WIDTH',
                      'NODE_BORDER_COLOR': 'NODE_BORDER_PAINT', 'NODE_BORDER_LINE_TYPE': 'NODE_BORDER_STROKE'}

    suid = networks.get_network_suid(network, base_url=base_url)

    # process mapping type
    mapping_type_name = MAPPING_TYPES[mapping_type] if mapping_type in MAPPING_TYPES else mapping_type

    # processs visual property, including common alternatives for vp names :)
    visual_prop_name = re.sub('\\s+', '_', visual_prop).upper()
    if visual_prop_name in PROPERTY_NAMES: visual_prop_name = PROPERTY_NAMES[visual_prop_name]

    # check visual prop name
    if visual_prop_name not in styles.get_visual_property_names(base_url=base_url):
        raise CyError(
            'Could not find ' + visual_prop_name + '. Run get_visual_property_names() to retrieve property names.')

    # check mapping column and get type
    tp = visual_prop_name.split('_')[0].lower()
    table = 'default' + tp
    res = commands.cyrest_get('networks/' + str(suid) + '/tables/' + table + '/columns', base_url=base_url)
    table_column_type = None
    for col in res:
        if col['name'] == table_column:
            table_column_type = col['type']
            break
    if table_column_type is None:
        raise CyError('Could not find ' + table_column + ' column in ' + table + ' table.')

    # construct visual property map
    visual_prop_map = {'mappingType': mapping_type_name, 'mappingColumn': table_column,
                       'mappingColumnType': table_column_type, 'visualProperty': visual_prop_name}
    if mapping_type_name == 'discrete':
        visual_prop_map['map'] = [{'key': col_val, 'value': prop_val}    for col_val, prop_val in zip(table_column_values, visual_prop_values)]
    elif mapping_type_name == 'continuous':
        # check for extra lesser and greater values
        prop_val_count = len(visual_prop_values)
        col_val_count = len(table_column_values)
        if prop_val_count - col_val_count == 2:
            matched_visual_prop_values = visual_prop_values[1:]
            points = [{'value': col_val, 'lesser': prop_val, 'equal': prop_val, 'greater': prop_val}    for col_val, prop_val in zip(table_column_values, matched_visual_prop_values)]

            # then correct extreme values
            points[0]['lesser'] = visual_prop_values[0]
            points[col_val_count - 1]['greater'] = visual_prop_values[-1]
        elif prop_val_count - col_val_count == 0:
            points = [{'value': col_val, 'lesser': prop_val, 'equal': prop_val, 'greater': prop_val}    for col_val, prop_val in zip(table_column_values, visual_prop_values)]
        else:
            error = 'Error: table.column.values and visual.prop.values don\'t match up.'
            sys.stderr.write(error)
            raise CyError(error)

        visual_prop_map['points'] = points

    return visual_prop_map

@cy_log
def update_style_mapping(style_name, mapping, base_url=DEFAULT_BASE_URL):
    """Update a visual property mapping in a style.

    Updates the visual property mapping, overriding any prior mapping. Creates a visual property mapping if it doesn't
    already exist in the style. Requires visual property mappings to be previously created, see ``map_visual_property``.

    Args:
        style_name (str): name for style
        mapping (dict): a single visual property mapping, see ``map_visual_property``
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str: ''

    Raises:
        CyError: if style doesn't exist
        TypeError: if mapping isn't a visual property mapping
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> update_style_mapping('galFiltered Style', map_visual_property('node label', 'name', 'p'))
        ''

    See Also:
        :meth:`map_visual_property`
    """
    visual_prop_name = mapping['visualProperty']

    # check if vp exists already
    res = commands.cyrest_get('styles/' + style_name + '/mappings', base_url=base_url)
    vp_list = [prop['visualProperty']   for prop in res]
    exists = visual_prop_name in vp_list

    if exists:
        res = commands.cyrest_put('styles/' + style_name + '/mappings/' + visual_prop_name, body=[mapping], base_url=base_url, require_json=False)
    else:
        res = commands.cyrest_post('styles/' + style_name + '/mappings', body=[mapping], base_url=base_url, require_json=False)
    time.sleep(MODEL_PROPAGATION_SECS)  # wait for attributes to be applied ... it looks like Cytoscape returns before this is complete [Cytoscape BUG]
    return res


# TODO: Note that R documentation for this is wrong ... we really do want a property name, not a map
@cy_log
def delete_style_mapping(style_name, visual_prop, base_url=DEFAULT_BASE_URL):
    """Delete a specified visual style mapping from specified style.

    Args:
        style_name (str): name for style
        visual_prop (str): name of visual property to delete
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' or None (if property doesn't exist)

    Raises:
        CyError: if style doesn't exist
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> delete_style_mapping('galFiltered Style', 'node label')
        ''
    """
    # check if vp exists already
    res = commands.cyrest_get('styles/' + style_name + '/mappings', base_url=base_url)
    vp_list = [prop['visualProperty']   for prop in res]
    exists = visual_prop in vp_list

    if exists:
        res = commands.cyrest_delete('styles/' + style_name + '/mappings/' + visual_prop, base_url=base_url, require_json=False)
    else:
        res = None
    return res
# TODO: Verify that it's OK to return None if the style doesn't exist ... maybe should be a CyError?

# TODO: Are we missing a get_style_mapping here?? ... probably ... I'm adding one to help with testing ...
@cy_log
def get_style_mapping(style_name, visual_prop, base_url=DEFAULT_BASE_URL):
    """Fetch a visual property mapping in a style.

    The property mapping is the same as a dict created by ``map_visual_property``.

    Args:
        style_name (str): name for style
        visual_prop (str): the name of the visual property
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        dict: see ``map_visual_property``

    Raises:
        CyError: if style or property name doesn't exist
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> get_style_mapping('galFiltered Style', 'node label')
        {"mappingType": "passthrough", "mappingColumn": "COMMON", "mappingColumnType": "String", "visualProperty": "NODE_LABEL"}

    See Also:
        :meth:`map_visual_property`
    """
    # check if vp exists already
    res = commands.cyrest_get('styles/' + style_name + '/mappings', base_url=base_url)
    for prop in res:
        if prop['visualProperty'] == visual_prop:
            return prop
    raise CyError('Property "' + visual_prop + '" does not exist in style "' + style_name + '"')

# TODO: Are we missing a get_style_all_mappings here?? ... probably ... I'm adding one to help with testing ...
@cy_log
def get_style_all_mappings(style_name, base_url=DEFAULT_BASE_URL):
    """Fetch all visual property mapping in a style.

    The property mappings are the same as a dict created by ``map_visual_property``.

    Args:
        style_name (str): name for style
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        list: list of dicts of the type created by ``map_visual_property``

    Raises:
        CyError: if style or property name doesn't exist
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> get_style_all_mappings('galFiltered Style')
        [{"mappingType": "passthrough", "mappingColumn": "name", "mappingColumnType": "String", "visualProperty": "NODE_LABEL"},
         {"mappingType": "passthrough", "mappingColumn": "interaction", "mappingColumnType": "String", "visualProperty": "EDGE_LABEL"}]

    See Also:
        :meth:`map_visual_property`
    """
    res = commands.cyrest_get('styles/' + style_name + '/mappings', base_url=base_url)
    return res

# ==============================================================================
# II. Specific Functions
# ==============================================================================
# II.a. Node Properties
# Pattern: (1) prepare map_visual_property, (2) call update_style_mapping()
# ------------------------------------------------------------------------------

# TODO: R documented colors list incorrectly
@cy_log
def set_node_border_color_mapping(table_column, table_column_values=None, colors=None, mapping_type='c', default_color=None, style_name='default', network=None, base_url=DEFAULT_BASE_URL):
    """Map table column values to colors to set the node border color.

    Args:
        table_column (str): Name of Cytoscape table column to map values from
        table_column_values (list): List of values from Cytoscape table to be used in mapping
        colors (list): list of hex colors
        mapping_type (str): continuous, discrete or passthrough (c,d,p); default is continuous
        default_color (str): Hex color to set as default
        style_name (str): name for style
        network (SUID or str or None): Name or SUID of a network or view. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' if successful or None if error

    Raises:
        CyError: if table column doesn't exist, table column values doesn't match values list, or invalid style name, network or mapping type
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> set_node_border_color_mapping('AverageShortestPathLength', [1.0, 16.36], ['#FBE723', '#440256'], style_name='galFiltered Style')
        ''
        >>> set_node_border_color_mapping('Degree', ['1', '2'], ['#FFFF00', '#00FF00'], 'd', style_name='galFiltered Style')
        ''
        >>> set_node_border_color_mapping('ColorCol', mapping_type='p', default_color='#654321', style_name='galFiltered Style')
        ''
    """
    for color in colors or []:
        if is_not_hex_color(color):
            return None # TODO: Should we be throwing an exception?

    # set default
    if default_color is not None:
        style_defaults.set_node_border_color_default(default_color, style_name, base_url=base_url)
# TODO: An error here will be missed ... shouldn't this throw an exception?

    return _update_style_mapping('NODE_BORDER_PAINT', table_column, table_column_values, colors, mapping_type, style_name, network, base_url)


def set_node_border_opacity_mapping(table_column, table_column_values=None, opacities=None, mapping_type='c', default_opacity=None, style_name='default', network=None, base_url=DEFAULT_BASE_URL):
    """Set opacity for node border only.

    Args:
        table_column (str): Name of Cytoscape table column to map values from
        table_column_values (list): List of values from Cytoscape table to be used in mapping
        opacities (list): int values between 0 and 255; 0 is invisible
        mapping_type (str): continuous, discrete or passthrough (c,d,p); default is continuous
        default_opacity (int): Opacity value to set as default for all unmapped values
        style_name (str): name for style
        network (SUID or str or None): Name or SUID of a network or view. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' if successful or None if error

    Raises:
        CyError: if table column doesn't exist, table column values doesn't match values list, or invalid style name, network or mapping type
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> set_node_border_opacity_mapping('AverageShortestPathLength', table_column_values=[1.0, 16.36], opacities=[50, 100], style_name='galFiltered Style')
        ''
        >>> set_node_border_opacity_mapping('Degree', table_column_values=['1', '2'], opacities=[50, 100], mapping_type='d', style_name='galFiltered Style')
        ''
        >>> set_node_border_opacity_mapping('PassthruCol', mapping_type='p', default_opacity=225, style_name='galFiltered Style')
        ''
    """
    if not table_column_exists(table_column, 'node', network=network, base_url=base_url):
        raise CyError('Table column does not exist. Please try again.')

    for o in opacities or []:
        if o < 0 or o > 255:
            sys.stderr.write('Error: opacities must be between 0 and 255.')
            return None

    if default_opacity is not None:
        if default_opacity < 0 or default_opacity > 255:
            sys.stderr.write('Error: opacity must be between 0 and 255.')
            return None
        style_defaults.set_visual_property_default({'visualProperty': 'NODE_BORDER_TRANSPARENCY', 'value': str(default_opacity)}, style_name=style_name, base_url=base_url)

    return _update_style_mapping('NODE_BORDER_TRANSPARENCY', table_column, table_column_values, opacities, mapping_type, style_name, network, base_url)


def set_node_border_width_mapping(table_column, table_column_values=None, widths=None, mapping_type='c', default_width=None, style_name='default', network=None, base_url=DEFAULT_BASE_URL):
    """Map table column values to widths to set the node border width.

    Args:
        table_column (str): Name of Cytoscape table column to map values from
        table_column_values (list): List of values from Cytoscape table to be used in mapping
        widths (list): List of width values to map to ``table_column_values``
        mapping_type (str): continuous, discrete or passthrough (c,d,p); default is continuous
        default_width (int): Width value to set as default for all unmapped values
        style_name (str): name for style
        network (SUID or str or None): Name or SUID of a network or view. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' if successful or None if error

    Raises:
        CyError: if table column doesn't exist, table column values doesn't match values list, or invalid style name, network or mapping type
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> set_node_border_width_mapping('AverageShortestPathLength', table_column_values=[1.0, 16.36], widths=[5, 10], style_name='galFiltered Style')
        ''
        >>> set_node_border_width_mapping('Degree', table_column_values=['1', '2'], widths=[5, 10], mapping_type='d', style_name='galFiltered Style')
        ''
        >>> set_node_border_width_mapping('PassthruCol', mapping_type='p', default_width=3, style_name='galFiltered Style')
        ''
    """
    # set default
    if default_width is not None:
        style_defaults.set_node_border_width_default(default_width, style_name, base_url=base_url)

    return _update_style_mapping('NODE_BORDER_WIDTH', table_column, table_column_values, widths, mapping_type, style_name, network, base_url)


def set_node_color_mapping(table_column, table_column_values=None, colors=None, mapping_type='c', default_color=None, style_name='default', network=None, base_url=DEFAULT_BASE_URL):
    """Map table column values to colors to set the node fill color.

    Args:
        table_column (str): Name of Cytoscape table column to map values from
        table_column_values (list): List of values from Cytoscape table to be used in mapping
        colors (list): list of hex colors to map to ``table_column_values``
        mapping_type (str): continuous, discrete or passthrough (c,d,p); default is continuous
        default_color (str): Hex color to set as default
        style_name (str): name for style
        network (SUID or str or None): Name or SUID of a network or view. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' if successful or None if error

    Raises:
        CyError: if table column doesn't exist, table column values doesn't match values list, or invalid style name, network or mapping type
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> set_node_color_mapping('AverageShortestPathLength', [1.0, 16.36], ['#FBE723', '#440256'], style_name='galFiltered Style')
        ''
        >>> set_node_color_mapping('Degree', ['1', '2'], ['#FFFF00', '#00FF00'], 'd', style_name='galFiltered Style')
        ''
        >>> set_node_color_mapping('ColorCol', mapping_type='p', default_color='#654321', style_name='galFiltered Style')
        ''
    """
    # check if colors are formatted correctly
    for color in colors or []:
        if is_not_hex_color(color):
            return None  # TODO: Should we be throwing an exception?

    # set default
    if default_color is not None:
        style_defaults.set_node_color_default(default_color, style_name, base_url=base_url)
    # TODO: An error here will be missed ... shouldn't this throw an exception?

    return _update_style_mapping('NODE_FILL_COLOR', table_column, table_column_values, colors, mapping_type,
                                 style_name, network, base_url)


def set_node_combo_opacity_mapping(table_column, table_column_values=None, opacities=None, mapping_type='c', default_opacity=None, style_name='default', network=None, base_url=DEFAULT_BASE_URL):
    """Set opacity for node fill, border and label all together.

    Args:
        table_column (str): Name of Cytoscape table column to map values from
        table_column_values (list): List of values from Cytoscape table to be used in mapping
        opacities (list): int values between 0 and 255; 0 is invisible
        mapping_type (str): continuous, discrete or passthrough (c,d,p); default is continuous
        default_opacity (int): Opacity value to set as default for all unmapped values
        style_name (str): name for style
        network (SUID or str or None): Name or SUID of a network or view. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' if successful or None if error

    Raises:
        CyError: if table column doesn't exist, table column values doesn't match values list, or invalid style name, network or mapping type
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> set_node_combo_opacity_mapping('AverageShortestPathLength', table_column_values=[1.0, 16.36], opacities=[50, 100], style_name='galFiltered Style')
        ''
        >>> set_node_combo_opacity_mapping('Degree', table_column_values=['1', '2'], opacities=[50, 100], mapping_type='d', style_name='galFiltered Style')
        ''
        >>> set_node_combo_opacity_mapping('PassthruCol', mapping_type='p', default_opacity=225, style_name='galFiltered Style')
        ''
    """
    if not table_column_exists(table_column, 'node', network=network, base_url=base_url):
        raise CyError('Table column does not exist. Please try again.')
        # TODO: This check wasn't in the R version, but probably should be

    for o in opacities or []:
        if o < 0 or o > 255:
            sys.stderr.write('Error: opacities must be between 0 and 255.')
            return None

    if default_opacity is not None:
        if default_opacity < 0 or default_opacity > 255:
            sys.stderr.write('Error: opacity must be between 0 and 255.')
            return None
        style_defaults.set_visual_property_default(
            {'visualProperty': 'NODE_TRANSPARENCY', 'value': str(default_opacity)}, style_name=style_name,
            base_url=base_url)
        style_defaults.set_visual_property_default(
            {'visualProperty': 'NODE_BORDER_TRANSPARENCY', 'value': str(default_opacity)}, style_name=style_name,
            base_url=base_url)
        style_defaults.set_visual_property_default(
            {'visualProperty': 'NODE_LABEL_TRANSPARENCY', 'value': str(default_opacity)}, style_name=style_name,
            base_url=base_url)

    # TODO: function results are ignored ... shouldn't we be capturing them?
    _update_style_mapping('NODE_TRANSPARENCY', table_column, table_column_values, opacities, mapping_type,
                          style_name, network, base_url)
    _update_style_mapping('NODE_BORDER_TRANSPARENCY', table_column, table_column_values, opacities, mapping_type,
                          style_name, network, base_url)
    res = _update_style_mapping('NODE_LABEL_TRANSPARENCY', table_column, table_column_values, opacities, mapping_type,
                          style_name, network, base_url)
    return res

def set_node_fill_opacity_mapping(table_column, table_column_values=None, opacities=None, mapping_type='c', default_opacity=None, style_name='default', network=None, base_url=DEFAULT_BASE_URL):
    """Set opacity for node fill only.

    Args:
        table_column (str): Name of Cytoscape table column to map values from
        table_column_values (list): List of values from Cytoscape table to be used in mapping
        opacities (list): int values between 0 and 255; 0 is invisible
        mapping_type (str): continuous, discrete or passthrough (c,d,p); default is continuous
        default_opacity (int): Opacity value to set as default for all unmapped values
        style_name (str): name for style
        network (SUID or str or None): Name or SUID of a network or view. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' if successful or None if error

    Raises:
        CyError: if table column doesn't exist, table column values doesn't match values list, or invalid style name, network or mapping type
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> set_node_fill_opacity_mapping('AverageShortestPathLength', table_column_values=[1.0, 16.36], opacities=[50, 100], style_name='galFiltered Style')
        ''
        >>> set_node_fill_opacity_mapping('Degree', table_column_values=['1', '2'], opacities=[50, 100], mapping_type='d', style_name='galFiltered Style')
        ''
        >>> set_node_fill_opacity_mapping('PassthruCol', mapping_type='p', default_opacity=225, style_name='galFiltered Style')
        ''
    """
    if not table_column_exists(table_column, 'node', network=network, base_url=base_url):
        raise CyError('Table column does not exist. Please try again.')

    for o in opacities or []:
        if o < 0 or o > 255:
            sys.stderr.write('Error: opacities must be between 0 and 255.')
            return None

    if default_opacity is not None:
        if default_opacity < 0 or default_opacity > 255:
            sys.stderr.write('Error: opacity must be between 0 and 255.')
            return None
        style_defaults.set_visual_property_default({'visualProperty': 'NODE_TRANSPARENCY', 'value': str(default_opacity)}, style_name=style_name, base_url=base_url)

    return _update_style_mapping('NODE_TRANSPARENCY', table_column, table_column_values, opacities, mapping_type, style_name, network, base_url)

def set_node_font_face_mapping(table_column, table_column_values=None, fonts=None, mapping_type='d', default_font=None, style_name='default', network=None, base_url=DEFAULT_BASE_URL):
    """Sets font face for node labels.

    Args:
        table_column (str): Name of Cytoscape table column to map values from
        table_column_values (list): List of values from Cytoscape table to be used in mapping
        fonts (list): List of string specifications of font face, style and size, e.g., ["SansSerif,plain,12", "Dialog,plain,10"]
        mapping_type (str): discrete or passthrough (d,p); default is discrete
        default_font (str): String specification of font face, style and size, e.g., "SansSerif,plain,12" or "Dialog,plain,10"
        style_name (str): name for style
        network (SUID or str or None): Name or SUID of a network or view. Default is the
            "current" network active in Cytoscape.
        base_url (str): Ignore unless you need to specify a custom domain,
            port or version to connect to the CyREST API. Default is http://localhost:1234
            and the latest version of the CyREST API supported by this version of py4cytoscape.

    Returns:
        str or None: '' if successful or None if error

    Raises:
        CyError: if table column doesn't exist, table column values doesn't match values list, or invalid style name, network or mapping type
        requests.exceptions.RequestException: if can't connect to Cytoscape or Cytoscape returns an error

    Examples:
        >>> set_node_font_face_mapping('Degree', table_column_values=['1', '2'], fonts=['Arial,plain,12', 'Arial Bold,bold,12'], mapping_type='d', style_name='galFiltered Style')
        ''
        >>> set_node_font_face_mapping('PassthruCol', mapping_type='p', default_font='Arial,plain,12', style_name='galFiltered Style')
        ''
    """
    if not table_column_exists(table_column, 'node', network=network, base_url=base_url):
        raise CyError('Table column does not exist. Please try again.')

    if default_font is not None:
        style_defaults.set_visual_property_default({'visualProperty': 'NODE_LABEL_FONT_FACE', 'value': default_font}, style_name=style_name, base_url=base_url)

    return _update_style_mapping('NODE_LABEL_FONT_FACE', table_column, table_column_values, fonts, mapping_type, style_name, network, base_url, supported_mappings=['d', 'p'])









def _update_style_mapping(visual_prop_name, table_column, table_column_values, range_map, mapping_type, style_name, network, base_url, supported_mappings=['c', 'd', 'p']):
    if range_map is not None: range_map = [str(x) for x in range_map] # CyREST requires strings

    # perform mapping
    if mapping_type in ['continuous', 'c', 'interpolate']:
        if 'c' in supported_mappings:
            mvp = map_visual_property(visual_prop_name, table_column, 'c', table_column_values, range_map,
                                      network=network,
                                      base_url=base_url)
        else:
            raise CyError('Continuous mapping of ' + visual_prop_name + ' values is not supported.')
    elif mapping_type in ['discrete', 'd', 'lookup']:
        if 'd' in supported_mappings:
            mvp = map_visual_property(visual_prop_name, table_column, 'd', table_column_values, range_map,
                                      network=network,
                                      base_url=base_url)
        else:
            raise CyError('Discrete mapping of ' + visual_prop_name + ' values is not supported.')
    elif mapping_type in ['passthrough', 'p']:
        if 'p' in supported_mappings:
            mvp = map_visual_property(visual_prop_name, table_column, 'p', network=network, base_url=base_url)
        else:
            raise CyError('Passthrough mapping of ' + visual_prop_name + ' values is not supported.')
    else:
        # TODO: Do we want to report this way?
        sys.stderr.write('mapping_type not recognized.')
        return None

    res = update_style_mapping(style_name, mvp, base_url=base_url)
    return res