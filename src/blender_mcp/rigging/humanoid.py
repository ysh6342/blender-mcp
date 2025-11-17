# src/blender_mcp/rigging/humanoid.py
# Core logic for humanoid rig detection, normalization, and inspection.

import bpy
from typing import Optional, List, Dict, Any, Literal, Tuple

# --- Constants for Bone Name Detection ---

# Heuristics for Mixamo bone names (lowercase for case-insensitive matching)
MIXAMO_BONE_MAP = {
    "hips": "hips",
    "spine": "spine",
    "spine1": "spine1",
    "spine2": "spine2",
    "neck": "neck",
    "head": "head",
    "leftshoulder": "leftshoulder",
    "leftarm": "leftarm",
    "leftforearm": "leftforearm",
    "lefthand": "lefthand",
    "rightshoulder": "rightshoulder",
    "rightarm": "rightarm",
    "rightforearm": "rightforearm",
    "righthand": "righthand",
    "leftupleg": "leftupleg",
    "leftleg": "leftleg",
    "leftfoot": "leftfoot",
    "lefttoebase": "lefttoebase",
    "rightupleg": "rightupleg",
    "rightleg": "rightleg",
    "rightfoot": "rightfoot",
    "righttoebase": "righttoebase",
}

# --- Type Definitions ---

RigType = Literal["mesh_only", "mixamo", "generic_humanoid", "unknown"]

class NormalizedHumanoid:
    """A standardized representation of a humanoid rig."""
    def __init__(self):
        self.rig_type: RigType = "unknown"
        self.armature_name: Optional[str] = None
        self.mesh_name: Optional[str] = None
        self.has_armature_modifier: bool = False
        self.vertex_count: int = 0
        
        # Core bone structure
        self.bones: Dict[str, Optional[str]] = {
            "hips": None,
            "head": None,
            "hand_l": None,
            "hand_r": None,
        }
        self.bone_chains: Dict[str, List[str]] = {
            "spine": [],
            "arm_l": [],
            "arm_r": [],
            "leg_l": [],
            "leg_r": [],
        }
        
        # Finger details
        self.fingers_l: Dict[str, List[str]] = {}
        self.fingers_r: Dict[str, List[str]] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the normalized rig data to a dictionary."""
        return {
            "rig_type": self.rig_type,
            "armature_name": self.armature_name,
            "mesh_name": self.mesh_name,
            "mesh_info": {
                "vertex_count": self.vertex_count,
                "has_armature_modifier": self.has_armature_modifier,
            },
            "structure": {
                "bones": self.bones,
                "chains": self.bone_chains,
            },
            "hands": {
                "left": {
                    "hand_bone": self.bones.get("hand_l"),
                    "fingers": self.fingers_l,
                },
                "right": {
                    "hand_bone": self.bones.get("hand_r"),
                    "fingers": self.fingers_r,
                },
            }
        }

# --- Helper Functions ---

def find_best_humanoid_candidate() -> Tuple[Optional[bpy.types.Object], Optional[bpy.types.Object]]:
    """
    Finds the most likely humanoid mesh and its associated armature.
    
    Returns:
        A tuple of (mesh_object, armature_object).
    """
    armature_obj = None
    mesh_obj = None

    # Find the armature with the most bones, likely the main character rig
    max_bones = 0
    for obj in bpy.context.scene.objects:
        if obj.type == 'ARMATURE' and len(obj.data.bones) > max_bones:
            max_bones = len(obj.data.bones)
            armature_obj = obj

    # Find the mesh with the most vertices, likely the character body
    max_verts = 0
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            # If an armature was found, prefer a mesh that uses it
            if armature_obj:
                for modifier in obj.modifiers:
                    if modifier.type == 'ARMATURE' and modifier.object == armature_obj:
                        mesh_obj = obj
                        break
                if mesh_obj:
                    break
            # Fallback: find the mesh with the most vertices
            if len(obj.data.vertices) > max_verts:
                max_verts = len(obj.data.vertices)
                mesh_obj = obj
                
    return mesh_obj, armature_obj

def get_armature_modifier(mesh: bpy.types.Object) -> Optional[bpy.types.ArmatureModifier]:
    """Gets the first active armature modifier on a mesh object."""
    if not mesh or mesh.type != 'MESH':
        return None
    for modifier in mesh.modifiers:
        if modifier.type == 'ARMATURE' and modifier.object:
            return modifier
    return None

def get_bone_children_recursive(bone: bpy.types.Bone) -> List[bpy.types.Bone]:
    """Recursively gets all children of a bone."""
    children = []
    for child in bone.children:
        children.append(child)
        children.extend(get_bone_children_recursive(child))
    return children

# --- Rig Detection and Normalization ---

def detect_rig_type(armature_obj: Optional[bpy.types.Object]) -> RigType:
    """
    Detects the type of rig based on bone naming conventions.
    """
    if not armature_obj:
        return "mesh_only"

    bone_names = [b.name.lower() for b in armature_obj.data.bones]
    mixamo_hits = 0
    
    for name in bone_names:
        # Mixamo bones are often prefixed with 'mixamorig:'
        if "mixamorig:" in name:
            mixamo_hits += 1

    if mixamo_hits > 5:  # Heuristic: if we find a few key Mixamo bones, it's a Mixamo rig
        return "mixamo"
    
    if len(bone_names) > 10: # Heuristic: if it has a decent number of bones, it's a generic humanoid
        return "generic_humanoid"

    return "unknown"

def build_normalized_description(mesh_obj: bpy.types.Object, armature_obj: Optional[bpy.types.Object]) -> NormalizedHumanoid:
    """
    Builds a normalized description of a humanoid rig.
    """
    norm = NormalizedHumanoid()
    if mesh_obj:
        norm.mesh_name = mesh_obj.name
        norm.vertex_count = len(mesh_obj.data.vertices)
        armature_mod = get_armature_modifier(mesh_obj)
        if armature_mod:
            norm.has_armature_modifier = True
            # If armature wasn't provided, get it from the modifier
            if not armature_obj:
                armature_obj = armature_mod.object

    if not armature_obj:
        norm.rig_type = "mesh_only"
        return norm

    norm.armature_name = armature_obj.name
    norm.rig_type = detect_rig_type(armature_obj)
    
    # --- Bone Mapping (Heuristics) ---
    
    bones = armature_obj.data.bones
    
    # Simple mapping for Mixamo
    if norm.rig_type == "mixamo":
        bone_map = {b.name.lower().split(':')[-1]: b.name for b in bones}
        norm.bones["hips"] = bone_map.get("hips")
        norm.bones["head"] = bone_map.get("head")
        norm.bones["hand_l"] = bone_map.get("lefthand")
        norm.bones["hand_r"] = bone_map.get("righthand")
        
        # Build chains
        if norm.bones["hips"]:
            hips_bone = bones.get(norm.bones["hips"])
            # This is a simplified chain build; a real one would traverse parents
            norm.bone_chains["spine"] = [b.name for b in hips_bone.children_recursive if "spine" in b.name.lower()]
    
    # TODO: Add heuristics for "generic_humanoid" based on position and hierarchy
    # For now, we'll leave it sparse for non-Mixamo rigs.
    
    return norm


# --- Main Inspection Function ---

def inspect_humanoid_rig(
    mesh_name: Optional[str] = None,
    armature_name: Optional[str] = None,
    origin_hint: str = "auto"
) -> Dict[str, Any]:
    """
    Inspects the scene for a humanoid character, detects its rig structure,
    and returns a normalized description.

    This is the core implementation function called by the addon handler.
    """
    mesh_obj = bpy.data.objects.get(mesh_name) if mesh_name else None
    armature_obj = bpy.data.objects.get(armature_name) if armature_name else None

    if not mesh_obj and not armature_obj:
        mesh_obj, armature_obj = find_best_humanoid_candidate()

    if not mesh_obj:
        return {"error": "Could not find a suitable mesh object in the scene."}

    normalized_rig = build_normalized_description(mesh_obj, armature_obj)

    return normalized_rig.to_dict()