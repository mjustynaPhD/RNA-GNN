import os
import Bio
import Bio.PDB
import numpy as np
from torch import Tensor
from constants import REV_ATOM_TYPES, RIBOSE, BASES


class SampleToPDB():
    def __init__(self):
        pass

    def to(self, format: str, sample, path, name, post_fix:str=''):
        # Convert sample to the desired format
        unique_batches = np.unique(sample.batch.cpu().numpy())
        assert format in ['pdb', 'xyz', 'trafl'], f"Invalid format: {format}. Accepted formats: 'pdb', 'xyz', 'trafl'"
        for batch in unique_batches:
            mask = sample.batch == batch
            try:
                if format == 'pdb':
                    self.write_pdb(sample.x[mask], path, name[batch])
                elif format == 'xyz':
                    self.write_xyz(sample.x[mask], path, name[batch], post_fix)
                elif format == 'trafl':
                    self.write_trafl(sample.x[mask], path, name[batch])
            except ValueError as e:
                print("Cannot save molecules with missing P atom.")

    def write_xyz(self, x, path, name, post_fix:str='', rnd_dig:int=4):
        atoms_pos, atom_names = self.get_atoms_pos_and_types(x)

        name = name.replace(".pdb", "")
        name = name + post_fix
        name = name + '.xyz' if not name.endswith('.xyz') else name
        # Save the structure as a xyz file
        os.makedirs(path, exist_ok=True)
        out_path = os.path.join(path, name)
        with open(out_path, 'w') as f:
            f.write(f"{len(atoms_pos)}\n")
            f.write(f"{name}\n")
            for atom, pos in zip(atom_names, atoms_pos):
                f.write(f"{atom} {round(pos[0], rnd_dig)} {round(pos[1], rnd_dig)} {round(pos[2], rnd_dig)}\n")

    def write_trafl(self, x: Tensor, path:str, name:str, post_fix:str='', rnd_dig:int=4):
        """The trafl format was described in SimRNA Manual. Here is the quote:
        "The format of coordinates line is just:
        x1 y1 z1 x2 y2 z2 … xN yN zN
        The coordinates of the subsequent points corresponds to the following order of the atoms: P, C4’,
        N(N1 or N9 for pyrimidine or purine, respectively), B1 (C2), B2 (C4 or C6 for pyrimidine or purine,
        respectively). In general, the coordinate line will contain 5*numberOfNucleotides points, so
        3*5*numberOfNucleotides coordinate items (in 3D space: 3 coordinates per atom, 5 atoms per
        residue; hence 15 coordinates per residue)." - SimRNA Manual

        Args:
            x (Tensor): input tensor of coordinates and atom types
            path (_type_): Path were output file should be saved
            name (_type_): Name of the output file
            post_fix (str, optional): Postfix added to the name of file (if any). Defaults to ''.
            rnd_dig (int, optional): Round coordinates to n decimal points. Defaults to 4.
        Raises:
            ValueError: If the number of atoms is not divisible by 5. The number of atoms should be a multiple of 5. Cannot save to trafl with missing P atom.
        """
        atoms_pos, atom_names = self.get_atoms_pos_and_types(x)
        atom_names = np.array(atom_names)
        if len(atoms_pos) % 5 != 0:
            raise ValueError("The number of atoms is not divisible by 5. The number of atoms should be a multiple of 5. Cannot save to trafl with missing P atom.")
        atoms_pos = atoms_pos.reshape(-1, 5, 3)
        atom_names = atom_names.reshape(-1, 5)
        p_atom = x[:, -9].cpu().numpy()
        p_c4p_c2_c46_n19 = x[:, -4:].cpu().numpy()
        p_c4p_c2_c46_n19 = np.concatenate([p_atom.reshape(-1, 1), p_c4p_c2_c46_n19], axis=1)
        p_c4p_c2_c46_n19 = p_c4p_c2_c46_n19.reshape(-1, 5, 5)

        name = name.replace(".pdb", "")
        name = name + post_fix
        name = name + '.trafl' if not name.endswith('.trafl') else name
        # Save the structure as a trafl file
        os.makedirs(path, exist_ok=True)
        out_path = os.path.join(path, name)
        c=0
        with open(out_path, 'w') as f:
            header = f"1 1 0 0 0"
            f.write(header + "\n")
            for atom, pos, orders in zip(atom_names, atoms_pos, p_c4p_c2_c46_n19):
                argmaxs = np.argmax(orders, axis=1)
                save_order = np.array([
                    np.where(argmaxs == 0)[0], # P
                    np.where(argmaxs == 1)[0], # C4'
                    np.where(argmaxs == 4)[0], # N1 or N9
                    np.where(argmaxs == 2)[0], # C2
                    np.where(argmaxs == 3)[0] # C4 or C6
                ]).flatten()
                for atom_name, atom_pos in zip(atom[save_order], pos[save_order]):
                    f.write(f" {atom_pos[0]:.3f} {atom_pos[1]:.3f} {atom_pos[2]:.3f}")
                    c+=1
        pass

    def write_pdb(self, x, path, name):
        atoms_pos, atom_names = self.get_atoms_pos_and_types(x)
    
        structure = self.create_structure(atoms_pos, atom_names, name)
        
        name = name + '.pdb' if not name.endswith('.pdb') else name
        # Save the structure as a PDB file
        os.makedirs(path, exist_ok=True)
        out_path = os.path.join(path, name)
        io = Bio.PDB.PDBIO()
        io.set_structure(structure)
        io.save(out_path)

    def get_atoms_pos_and_types(self, x):
        atoms_pos = x[:, :3].cpu().numpy()
        atoms_pos *= 10
        atoms_types = x[:, 3:7].cpu().numpy()
        atom_names = [REV_ATOM_TYPES[np.argmax(atom)] for atom in atoms_types]
        return atoms_pos, atom_names


    def create_structure(self, coords, atoms, name):
        # Create an empty structure
        structure = Bio.PDB.Structure.Structure(name)
        
        # Create a model within the structure
        model = Bio.PDB.Model.Model(0)
        structure.add(model)
        
        # Create a chain within the model
        chain = Bio.PDB.Chain.Chain('A')
        model.add(chain)
        
        # Create atoms and add them to the chain
        residue_id = 1
        for coord, atom in zip(coords, atoms):
            residue_name = 'A' # atom.get_parent().get_resname()
            
            # Create a residue
            residue = Bio.PDB.Residue.Residue((' ', residue_id, ' '), residue_name, ' ')
            chain.add(residue)
            
            # Create an atom
            new_atom = Bio.PDB.Atom.Atom(atom, coord, 0, 0, ' ', atom, 0, ' ')
            residue.add(new_atom)
            residue_id += 1
        
        return structure
    
    def extract_structural_templates(self, path, name):
        # read the pdb file
        # extract the atom positions for ribose (with phosphate) and bases
        # save the extracted atoms as a xyz files
        ribose_atoms = []
        bases_atoms = {}

        structure = Bio.PDB.PDBParser().get_structure(name, path)
        for model in structure:
            for chain in model:
                for residue in chain:
                    if residue.get_resname() == 'A':
                        # Extract the atom positions for ribose (with phosphate) and bases
                        ribose = residue['C1\'']
                        phosphate = residue['P']
                        base = residue['N9']
                        # Save the extracted atoms as a xyz files
                        self.write_xyz(np.array([ribose.get_coord(), phosphate.get_coord(), base.get_coord()]), path, name, post_fix='_extracted')
                    else:
                        pass

        pass
        
