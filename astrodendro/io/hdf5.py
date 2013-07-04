# Licensed under an MIT open source license - see LICENSE

import numpy as np

# Helper functions:


def _parse_newick(string):

    items = {}

    # Find maximum level
    current_level = 0
    max_level = 0
    for i, c in enumerate(string):
        if c == '(':
            current_level += 1
        if c == ')':
            current_level -= 1
        max_level = max(max_level, current_level)

    # Loop through levels and construct tree
    for level in range(max_level, 0, -1):

        pairs = []

        current_level = 0
        for i, c in enumerate(string):
            if c == '(':
                current_level += 1
                if current_level == level:
                    start = i
            if c == ')':
                if current_level == level:
                    pairs.append((start, i))
                current_level -= 1

        for pair in pairs[::-1]:

            # Extract start and end of branch definition
            start, end = pair

            # Find the ID of the branch
            colon = string.find(":", end)
            branch_id = string[end + 1:colon]
            if branch_id == '':
                branch_id = 'trunk'
            else:
                branch_id = int(branch_id)

            # Add branch definition to overall definition
            items[branch_id] = eval("{%s}" % string[start + 1:end])

            # Remove branch definition from string
            string = string[:start] + string[end + 1:]

    new_items = {}

    def collect(d):
        for item in d:
            if item in items:
                collect(items[item])
                d[item] = (items[item], d[item])
        return

    collect(items['trunk'])

    return items['trunk']

# Import and export


def dendro_export_hdf5(d, filename):
    """Export the dendrogram 'd' to the HDF5 file 'filename'"""
    import h5py
    f = h5py.File(filename, 'w')

    f.attrs['n_dim'] = d.n_dim

    f.create_dataset('newick', data=d.to_newick())

    ds = f.create_dataset('index_map', data=d.index_map, compression=True)
    ds.attrs['CLASS'] = 'IMAGE'
    ds.attrs['IMAGE_VERSION'] = '1.2'
    ds.attrs['IMAGE_MINMAXRANGE'] = [d.index_map.min(), d.index_map.max()]

    ds = f.create_dataset('data', data=d.data, compression=True)
    ds.attrs['CLASS'] = 'IMAGE'
    ds.attrs['IMAGE_VERSION'] = '1.2'
    ds.attrs['IMAGE_MINMAXRANGE'] = [d.data.min(), d.data.max()]

    f.close()


def dendro_import_hdf5(filename):
    """Import 'filename' and construct a dendrogram from it"""
    import h5py
    from ..dendrogram import Dendrogram
    from ..structure import Structure
    h5f = h5py.File(filename, 'r')
    d = Dendrogram()
    d.n_dim = h5f.attrs['n_dim']
    d.data = h5f['data'].value
    d.index_map = h5f['index_map'].value
    d.structures_dict = {}

    flux_by_structure = {}
    indices_by_structure = {}

    def _construct_tree(repr):
        structures = []
        for idx in repr:
            structure_indices = indices_by_structure[idx]
            f = flux_by_structure[idx]
            if type(repr[idx]) == tuple:
                sub_structures_repr = repr[idx][0]  # Parsed representation of sub structures
                sub_structures = _construct_tree(sub_structures_repr)
                for i in sub_structures:
                    d.structures_dict[i.idx] = i
                b = Structure(structure_indices, f, children=sub_structures, idx=idx)
                # Correct merge levels - complicated because of the
                # order in which we are building the tree.
                # What we do is look at the heights of this branch's
                # 1st child as stored in the newick representation, and then
                # work backwards to compute the merge level of this branch
                first_child_repr = sub_structures_repr.itervalues().next()
                if type(first_child_repr) == tuple:
                    height = first_child_repr[1]
                else:
                    height = first_child_repr
                d.structures_dict[idx] = b
                structures.append(b)
            else:
                l = Structure(structure_indices, f, idx=idx)
                structures.append(l)
                d.structures_dict[idx] = l
        return structures

    # Do a fast iteration through d.data, adding the indices and data values
    # to the two dictionaries declared above:
    indices = np.indices(d.data.shape).reshape(d.data.ndim, np.prod(d.data.shape)).transpose()

    for coord in indices:
        coord = tuple(coord)
        idx = d.index_map[coord]
        if idx:
            try:
                flux_by_structure[idx].append(d.data[coord])
                indices_by_structure[idx].append(coord)
            except KeyError:
                flux_by_structure[idx] = [d.data[coord]]
                indices_by_structure[idx] = [coord]

    d.trunk = _construct_tree(_parse_newick(h5f['newick'].value))
    # To make the structure.level property fast, we ensure all the items in the
    # trunk have their level cached as "0"
    for structure in d.trunk:
        structure._level = 0  # See the @property level() definition in structure.py

    return d
