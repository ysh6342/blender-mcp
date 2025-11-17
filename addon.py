# Code created by Siddharth Ahuja: www.github.com/ahujasid © 2025

import bpy
import mathutils
import json
import threading
import socket
import time
import requests
import tempfile
import traceback
import os
import shutil
import zipfile
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty
import io
from contextlib import redirect_stdout, suppress
from typing import Optional, List, Dict, Any, Literal, Tuple

# --- Rigging Constants for Bone Name Detection ---

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

# --- Rigging Type Definitions ---

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

# --- Rigging Helper Functions ---

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
            if not armature_obj:
                armature_obj = armature_mod.object

    if not armature_obj:
        norm.rig_type = "mesh_only"
        return norm

    norm.armature_name = armature_obj.name
    norm.rig_type = detect_rig_type(armature_obj)
    
    bones = armature_obj.data.bones
    
    # --- Bone Mapping (Heuristics) ---
    bone_map = {b.name.lower().replace("_", "").replace("-", "").replace(" ", "").split(':')[-1]: b.name for b in bones}
    
    norm.bones["hips"] = bone_map.get("hips")
    norm.bones["head"] = bone_map.get("head")
    norm.bones["hand_l"] = bone_map.get("lefthand")
    norm.bones["hand_r"] = bone_map.get("righthand")
    
    # --- Chain & Finger Detection ---
    if norm.bones["hand_l"]:
        hand_bone_l = bones.get(norm.bones["hand_l"])
        for child in hand_bone_l.children:
            finger_name = next((f for f in ["thumb", "index", "middle", "ring", "pinky"] if f in child.name.lower()), None)
            if finger_name:
                chain = [child] + child.children_recursive
                norm.fingers_l[finger_name] = [b.name for b in chain]

    if norm.bones["hand_r"]:
        hand_bone_r = bones.get(norm.bones["hand_r"])
        for child in hand_bone_r.children:
            finger_name = next((f for f in ["thumb", "index", "middle", "ring", "pinky"] if f in child.name.lower()), None)
            if finger_name:
                chain = [child] + child.children_recursive
                norm.fingers_r[finger_name] = [b.name for b in chain]

    return norm


def rigging_inspect_humanoid_rig(
    mesh_name: Optional[str] = None,
    armature_name: Optional[str] = None,
    origin_hint: str = "auto"
) -> Dict[str, Any]:
    """
    Inspects the scene for a humanoid character, detects its rig structure,
    and returns a normalized description.
    """
    mesh_obj = bpy.data.objects.get(mesh_name) if mesh_name else None
    armature_obj = bpy.data.objects.get(armature_name) if armature_name else None

    if not mesh_obj and not armature_obj:
        mesh_obj, armature_obj = find_best_humanoid_candidate()

    if not mesh_obj:
        return {"error": "Could not find a suitable mesh object in the scene."}

    normalized_rig = build_normalized_description(mesh_obj, armature_obj)

    return normalized_rig.to_dict()

def rigging_auto_rig_meshy_character(
    mesh_name: Optional[str] = None,
    use_auto_rig_pro: bool = True,
    finger_segments: int = 3
) -> Dict[str, Any]:
    """
    Auto-rigs a mesh-only character. Uses Auto-Rig Pro if available,
    otherwise falls back to a basic bpy implementation.
    """
    # 1. Find the target mesh
    mesh_obj = bpy.data.objects.get(mesh_name) if mesh_name else find_best_humanoid_candidate()[0]
    if not mesh_obj:
        return {"error": "Could not find a suitable mesh to rig."}

    # 2. Check if it's already rigged
    inspection = rigging_inspect_humanoid_rig(mesh_name=mesh_obj.name)
    if inspection.get("rig_type") != "mesh_only":
        return {
            "status": "skipped",
            "message": f"Mesh '{mesh_obj.name}' already has an armature '{inspection.get('armature_name')}'. No action taken.",
            "details": inspection
        }

    # 3. Attempt to use Auto-Rig Pro if requested and available
    arp_was_used = False
    if use_auto_rig_pro:
        try:
            # Check if ARP is installed
            import auto_rig_pro
            arp_was_used = True
            
            return {
                "status": "success_placeholder",
                "message": f"Auto-Rig Pro was detected. A full implementation would now rig '{mesh_obj.name}'.",
                "armature_name": "TBD_by_ARP",
                "used_auto_rig_pro": True
            }

        except ImportError:
            pass

    # 4. Fallback to basic bpy implementation
    if not arp_was_used:
        # Create a new armature
        armature_data = bpy.data.armatures.new(f"{mesh_obj.name}_Rig")
        armature_obj = bpy.data.objects.new(armature_data.name, armature_data)
        bpy.context.scene.collection.objects.link(armature_obj)
        
        # Set armature to active object and enter edit mode
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = armature_obj.data.edit_bones

        # --- Create Bones based on Mesh Bounding Box ---
        # This is a very rough estimation
        min_z = mesh_obj.bound_box[0][2]
        max_z = mesh_obj.bound_box[6][2]
        center_x = (mesh_obj.bound_box[0][0] + mesh_obj.bound_box[6][0]) / 2
        
        hips_pos = (center_x, 0, min_z + (max_z - min_z) * 0.4)
        spine_pos = (center_x, 0, min_z + (max_z - min_z) * 0.6)
        neck_pos = (center_x, 0, min_z + (max_z - min_z) * 0.8)
        head_pos = (center_x, 0, max_z)

        # Spine
        hips = edit_bones.new('hips')
        hips.head = hips_pos
        hips.tail = spine_pos
        
        spine = edit_bones.new('spine')
        spine.head = spine_pos
        spine.tail = neck_pos
        spine.parent = hips
        
        neck = edit_bones.new('neck')
        neck.head = neck_pos
        neck.tail = head_pos
        neck.parent = spine

        head = edit_bones.new('head')
        head.head = head_pos
        head.tail = (head_pos[0], head_pos[1], head_pos[2] + 0.1)
        head.parent = neck

        # Arms
        for side in ('l', 'r'):
            x_mult = 1 if side == 'r' else -1
            
            shoulder_pos = (center_x + x_mult * 0.1, 0, neck_pos[2] - 0.05)
            elbow_pos = (center_x + x_mult * 0.3, 0, neck_pos[2] - 0.15)
            hand_pos = (center_x + x_mult * 0.5, 0, neck_pos[2] - 0.2)

            upper_arm = edit_bones.new(f'upper_arm.{side}')
            upper_arm.head = shoulder_pos
            upper_arm.tail = elbow_pos
            upper_arm.parent = spine

            lower_arm = edit_bones.new(f'lower_arm.{side}')
            lower_arm.head = elbow_pos
            lower_arm.tail = hand_pos
            lower_arm.parent = upper_arm

            hand = edit_bones.new(f'hand.{side}')
            hand.head = hand_pos
            hand.tail = (hand_pos[0] + x_mult * 0.05, hand_pos[1], hand_pos[2])
            hand.parent = lower_arm

        # Legs
        for side in ('l', 'r'):
            x_mult = 1 if side == 'r' else -1
            
            thigh_pos = (center_x + x_mult * 0.08, 0, hips_pos[2])
            calf_pos = (center_x + x_mult * 0.08, 0, min_z + (max_z - min_z) * 0.2)
            foot_pos = (center_x + x_mult * 0.08, 0, min_z)

            thigh = edit_bones.new(f'thigh.{side}')
            thigh.head = thigh_pos
            thigh.tail = calf_pos
            thigh.parent = hips

            calf = edit_bones.new(f'calf.{side}')
            calf.head = calf_pos
            calf.tail = foot_pos
            calf.parent = thigh

            foot = edit_bones.new(f'foot.{side}')
            foot.head = foot_pos
            foot.tail = (foot_pos[0], foot_pos[1] - 0.1, foot_pos[2])
            foot.parent = calf

        # Switch back to object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Parent mesh to armature with automatic weights
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')

        return {
            "status": "success",
            "message": f"Created a basic fallback rig for '{mesh_obj.name}' and applied automatic weights.",
            "armature_name": armature_obj.name,
            "used_auto_rig_pro": False,
            "bone_count": len(armature_obj.data.bones)
        }

    return {"error": "An unknown error occurred during auto-rigging."}

def rigging_ensure_finger_chains_for_hand(
    armature_name: Optional[str] = None,
    mesh_name: Optional[str] = None,
    side: Literal["L","R"] = "L",
    finger_segments: int = 3,
    fingers: list[str] = None
) -> Dict[str, Any]:
    """
    Ensures a given hand has a complete set of finger bones.
    """
    if fingers is None:
        fingers = ["thumb", "index", "middle", "ring", "pinky"]

    inspection = rigging_inspect_humanoid_rig(mesh_name=mesh_name, armature_name=armature_name)
    if inspection.get("error"):
        return inspection
    
    armature_obj = bpy.data.objects.get(inspection["armature_name"])
    if not armature_obj:
        return {"error": f"Could not find armature '{inspection['armature_name']}'."}

    side_suffix = f".{side.lower()}"
    hand_bone_name = f"hand{side_suffix}"
    
    if hand_bone_name not in armature_obj.data.bones:
         # Fallback for mixamo-style names
        hand_bone_name = inspection["hands"][side.lower()]["hand_bone"]
        if not hand_bone_name:
            return {"error": f"Could not find hand bone for side '{side}' in the rig."}

    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    edit_bones = armature_obj.data.edit_bones
    hand_bone = edit_bones.get(hand_bone_name)
    
    created_fingers = {}
    
    # Define approximate finger positions relative to the hand
    finger_positions = {
        "thumb": (0.0, -0.03, 0.02),
        "index": (0.0, -0.01, 0.05),
        "middle": (0.0, 0.0, 0.05),
        "ring": (0.0, 0.01, 0.05),
        "pinky": (0.0, 0.02, 0.04)
    }

    for finger_name in fingers:
        # Check if finger already exists
        if any(child.name.lower().startswith(finger_name) for child in hand_bone.children):
            created_fingers[finger_name] = "existed"
            continue

        # Create finger bones
        parent_bone = hand_bone
        for i in range(finger_segments):
            bone_name = f"{finger_name}_{i+1}{side_suffix}"
            new_bone = edit_bones.new(bone_name)
            
            if i == 0:
                start_pos = finger_positions.get(finger_name, (0,0,0))
                new_bone.head = hand_bone.tail + mathutils.Vector(start_pos)
            else:
                new_bone.head = parent_bone.tail
            
            new_bone.tail = (new_bone.head[0], new_bone.head[1] - 0.02, new_bone.head[2])
            new_bone.parent = parent_bone
            parent_bone = new_bone
        
        created_fingers[finger_name] = "created"

    bpy.ops.object.mode_set(mode='OBJECT')
    
    return {
        "status": "success",
        "message": f"Verified finger chains for side '{side}'.",
        "armature_name": armature_obj.name,
        "side": side,
        "finger_status": created_fingers
    }

def rigging_auto_weight_fingers_only(
    armature_name: Optional[str] = None,
    mesh_name: Optional[str] = None,
    side: Literal["L","R","both"] = "both",
    normalize: bool = True
) -> Dict[str, Any]:
    """
    Auto-weights finger bones for a given character.
    WARNING: This is a destructive operation. It will remove non-finger vertex groups.
    """
    inspection = rigging_inspect_humanoid_rig(mesh_name=mesh_name, armature_name=armature_name)
    if inspection.get("error"):
        return inspection

    armature_obj = bpy.data.objects.get(inspection["armature_name"])
    mesh_obj = bpy.data.objects.get(inspection["mesh_name"])

    if not armature_obj or not mesh_obj:
        return {"error": "Could not find armature or mesh object."}

    finger_bone_names = []
    if side in ["L", "both"]:
        for finger, bones in inspection["hands"]["left"]["fingers"].items():
            finger_bone_names.extend(bones)
    if side in ["R", "both"]:
        for finger, bones in inspection["hands"]["right"]["fingers"].items():
            finger_bone_names.extend(bones)

    if not finger_bone_names:
        return {"status": "skipped", "message": "No finger bones found to weight."}

    # --- Destructive weighting process ---
    
    # 1. Remove existing armature modifiers to avoid conflicts
    for mod in mesh_obj.modifiers:
        if mod.type == 'ARMATURE':
            mesh_obj.modifiers.remove(mod)

    # 2. Unparent the mesh
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

    # 3. Select the mesh and armature
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    # 4. Parent with automatic weights - this will create groups for all bones
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')

    # 5. Remove vertex groups that are NOT finger bones
    for vgroup in mesh_obj.vertex_groups:
        if vgroup.name not in finger_bone_names:
            mesh_obj.vertex_groups.remove(vgroup)

    # 6. Normalize weights if requested
    if normalize:
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
        bpy.ops.object.mode_set(mode='OBJECT')

    return {
        "status": "success",
        "message": f"Applied automatic weights for {len(finger_bone_names)} finger bones. " \
                   "WARNING: This was a destructive operation that may have altered existing weights.",
        "weighted_finger_bones": finger_bone_names,
    }

def rigging_arp_add_or_fix_finger_rig(
    armature_name: Optional[str] = None,
    mesh_name: Optional[str] = None,
    side: Literal["L","R","both"] = "both"
) -> Dict[str, Any]:
    """
    Uses Auto-Rig Pro to add/fix fingers if available.
    Falls back to the manual method otherwise.
    """
    try:
        import auto_rig_pro
        return {
            "status": "success_placeholder",
            "message": "Auto-Rig Pro detected. A full implementation would use its API to rig the fingers.",
            "method": "auto_rig_pro"
        }
    except ImportError:
        results = []
        sides_to_process = ["L", "R"] if side == "both" else [side]
        for s in sides_to_process:
            ensure_result = rigging_ensure_finger_chains_for_hand(armature_name, mesh_name, s)
            results.append(ensure_result)
            if ensure_result.get("status", "").startswith("success"):
                weight_result = rigging_auto_weight_fingers_only(armature_name, mesh_name, s)
                results.append(weight_result)
        
        return {
            "status": "success_fallback",
            "message": "Auto-Rig Pro not found. Used fallback to create and weight finger bones.",
            "method": "fallback",
            "fallback_results": results
        }

def rigging_rename_fingers_to_ue5(
    armature_name: Optional[str] = None,
    side: Literal["L","R","both"] = "both",
    include_body: bool = False,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Renames bones to be compatible with Unreal Engine 5.
    """
    inspection = rigging_inspect_humanoid_rig(armature_name=armature_name)
    if inspection.get("error"):
        return inspection

    armature_obj = bpy.data.objects.get(inspection["armature_name"])
    if not armature_obj:
        return {"error": f"Could not find armature '{inspection['armature_name']}'."}

    proposed_mappings = {}
    
    # --- Finger Renaming ---
    sides_to_process = ["l", "r"] if side == "both" else [side.lower()]
    for s in sides_to_process:
        finger_data = inspection["hands"][s]["fingers"]
        for finger_name, bone_chain in finger_data.items():
            for i, old_bone_name in enumerate(bone_chain):
                new_bone_name = f"{finger_name}_{i+1:02d}_{s}"
                if old_bone_name != new_bone_name:
                    proposed_mappings[old_bone_name] = new_bone_name

    # --- Body Renaming (Optional) ---
    if include_body:
        # This is a simplified mapping. A real implementation would be more robust.
        body_map = {
            "hips": "pelvis",
            "spine": "spine_01",
            "spine1": "spine_02",
            "spine2": "spine_03",
            "neck": "neck_01",
            "head": "head",
            "leftarm": "upperarm_l",
            "leftforearm": "lowerarm_l",
            "lefthand": "hand_l",
            "rightarm": "upperarm_r",
            "rightforearm": "lowerarm_r",
            "righthand": "hand_r",
            "leftupleg": "thigh_l",
            "leftleg": "calf_l",
            "leftfoot": "foot_l",
            "rightupleg": "thigh_r",
            "rightleg": "calf_r",
            "rightfoot": "foot_r",
        }
        # We need to find the bones from the inspection
        # This part is complex and depends on a more robust `build_normalized_description`
        # For now, we'll leave this as a placeholder.
        pass

    if dry_run:
        return {
            "status": "success_dry_run",
            "message": "Dry run complete. No bones were renamed.",
            "proposed_mappings": proposed_mappings
        }

    # --- Execute Renaming ---
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    edit_bones = armature_obj.data.edit_bones
    applied_mappings = {}

    for old_name, new_name in proposed_mappings.items():
        bone = edit_bones.get(old_name)
        if bone and new_name not in edit_bones:
            bone.name = new_name
            applied_mappings[old_name] = new_name

    bpy.ops.object.mode_set(mode='OBJECT')

    return {
        "status": "success",
        "message": f"Renamed {len(applied_mappings)} bones to UE5 standard.",
        "applied_mappings": applied_mappings
    }

def rigging_export_ue5_ready_fbx(
    filepath: str,
    armature_name: Optional[str] = None,
    mesh_name: Optional[str] = None,
    apply_scale: float = 1.0,
    use_tpose: bool = True,
    export_animations: bool = False
) -> Dict[str, Any]:
    """
    Exports a character as an FBX file with UE5-compatible settings.
    """
    if not filepath:
        return {"error": "A filepath must be provided for the FBX export."}

    # 1. Find and select the objects to export
    armature_obj = bpy.data.objects.get(armature_name)
    mesh_obj = bpy.data.objects.get(mesh_name)

    if not armature_obj or not mesh_obj:
        mesh_obj, armature_obj = find_best_humanoid_candidate()
    
    if not armature_obj or not mesh_obj:
        return {"error": "Could not auto-detect a suitable mesh and armature to export."}

    bpy.ops.object.select_all(action='DESELECT')
    armature_obj.select_set(True)
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    # 2. Optionally apply a T-pose
    if use_tpose:
        # This is a simplified T-pose. A real implementation would be more robust.
        if armature_obj.pose:
            for bone in armature_obj.pose.bones:
                bone.rotation_quaternion.identity()
                bone.rotation_euler.zero()
                bone.rotation_axis_angle[0] = 0
                bone.rotation_axis_angle[1] = 1
                bone.rotation_axis_angle[2] = 0
                bone.rotation_axis_angle[3] = 0


    # 3. Export FBX with UE5-friendly settings
    try:
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
            object_types={'ARMATURE', 'MESH'},
            apply_scale_options='FBX_SCALE_ALL',
            bake_anim=export_animations,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=export_animations,
            add_leaf_bones=False,
            primary_bone_axis='X',
            secondary_bone_axis='-Y',
            use_tspace=True,
        )
        return {
            "status": "success",
            "message": f"Successfully exported '{armature_obj.name}' and '{mesh_obj.name}' to '{filepath}'.",
            "filepath": filepath
        }
    except Exception as e:
        return {"error": f"FBX export failed: {str(e)}"}


bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to Claude via MCP",
    "category": "Interface",
}

RODIN_FREE_TRIAL_KEY = "k9TcfFoEhNd9cCPP2guHAHHHkctZHIRhZDywZ1euGUXwihbYLpOjQhofby80NJez"

# Add User-Agent as required by Poly Haven API
REQ_HEADERS = requests.utils.default_headers()
REQ_HEADERS.update({"User-Agent": "blender-mcp"})

class BlenderMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None

    def start(self):
        if self.running:
            print("Server is already running")
            return

        self.running = True

        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)

            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()

            print(f"BlenderMCP server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to start server: {str(e)}")
            self.stop()

    def stop(self):
        self.running = False

        # Close socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        # Wait for thread to finish
        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None

        print("BlenderMCP server stopped")

    def _server_loop(self):
        """Main server loop in a separate thread"""
        print("Server thread started")
        self.socket.settimeout(1.0)  # Timeout to allow for stopping

        while self.running:
            try:
                # Accept new connection
                try:
                    client, address = self.socket.accept()
                    print(f"Connected to client: {address}")

                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    # Just check running condition
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {str(e)}")
                    time.sleep(0.5)
            except Exception as e:
                print(f"Error in server loop: {str(e)}")
                if not self.running:
                    break
                time.sleep(0.5)

        print("Server thread stopped")

    def _handle_client(self, client):
        """Handle connected client"""
        print("Client handler started")
        client.settimeout(None)  # No timeout
        buffer = b''

        try:
            while self.running:
                # Receive data
                try:
                    data = client.recv(8192)
                    if not data:
                        print("Client disconnected")
                        break

                    buffer += data
                    try:
                        # Try to parse command
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''

                        # Execute command in Blender's main thread
                        def execute_wrapper():
                            try:
                                response = self.execute_command(command)
                                response_json = json.dumps(response)
                                try:
                                    client.sendall(response_json.encode('utf-8'))
                                except:
                                    print("Failed to send response - client disconnected")
                            except Exception as e:
                                print(f"Error executing command: {str(e)}")
                                traceback.print_exc()
                                try:
                                    error_response = {
                                        "status": "error",
                                        "message": str(e)
                                    }
                                    client.sendall(json.dumps(error_response).encode('utf-8'))
                                except:
                                    pass
                            return None

                        # Schedule execution in main thread
                        bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                    except json.JSONDecodeError:
                        # Incomplete data, wait for more
                        pass
                except Exception as e:
                    print(f"Error receiving data: {str(e)}")
                    break
        except Exception as e:
            print(f"Error in client handler: {str(e)}")
        finally:
            try:
                client.close()
            except:
                pass
            print("Client handler stopped")

    def execute_command(self, command):
        """Execute a command in the main Blender thread"""
        try:
            return self._execute_command_internal(command)

        except Exception as e:
            print(f"Error executing command: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def _execute_command_internal(self, command):
        """Internal command execution with proper context"""
        cmd_type = command.get("type")
        params = command.get("params", {})

        # Add a handler for checking PolyHaven status
        if cmd_type == "get_polyhaven_status":
            return {"status": "success", "result": self.get_polyhaven_status()}

        # Base handlers that are always available
        handlers = {
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_code": self.execute_code,
            "get_polyhaven_status": self.get_polyhaven_status,
            "get_hyper3d_status": self.get_hyper3d_status,
            "get_sketchfab_status": self.get_sketchfab_status,
            "rigging_inspect_humanoid_rig": rigging_inspect_humanoid_rig,
            "rigging_auto_rig_meshy_character": rigging_auto_rig_meshy_character,
            "rigging_ensure_finger_chains_for_hand": rigging_ensure_finger_chains_for_hand,
            "rigging_auto_weight_fingers_only": rigging_auto_weight_fingers_only,
            "rigging_arp_add_or_fix_finger_rig": rigging_arp_add_or_fix_finger_rig,
            "rigging_rename_fingers_to_ue5": rigging_rename_fingers_to_ue5,
            "rigging_export_ue5_ready_fbx": rigging_export_ue5_ready_fbx,
        }

        # Add Polyhaven handlers only if enabled
        if bpy.context.scene.blendermcp_use_polyhaven:
            polyhaven_handlers = {
                "get_polyhaven_categories": self.get_polyhaven_categories,
                "search_polyhaven_assets": self.search_polyhaven_assets,
                "download_polyhaven_asset": self.download_polyhaven_asset,
                "set_texture": self.set_texture,
            }
            handlers.update(polyhaven_handlers)

        # Add Hyper3d handlers only if enabled
        if bpy.context.scene.blendermcp_use_hyper3d:
            polyhaven_handlers = {
                "create_rodin_job": self.create_rodin_job,
                "poll_rodin_job_status": self.poll_rodin_job_status,
                "import_generated_asset": self.import_generated_asset,
            }
            handlers.update(polyhaven_handlers)

        # Add Sketchfab handlers only if enabled
        if bpy.context.scene.blendermcp_use_sketchfab:
            sketchfab_handlers = {
                "search_sketchfab_models": self.search_sketchfab_models,
                "download_sketchfab_model": self.download_sketchfab_model,
            }
            handlers.update(sketchfab_handlers)

        handler = handlers.get(cmd_type)
        if handler:
            try:
                print(f"Executing handler for {cmd_type}")
                result = handler(**params)
                print(f"Handler execution complete")
                return {"status": "success", "result": result}
            except Exception as e:
                print(f"Error in handler: {str(e)}")
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}



    def get_scene_info(self):
        """Get information about the current Blender scene"""
        try:
            print("Getting scene info...")
            # Simplify the scene info to reduce data size
            scene_info = {
                "name": bpy.context.scene.name,
                "object_count": len(bpy.context.scene.objects),
                "objects": [],
                "materials_count": len(bpy.data.materials),
            }

            # Collect minimal object information (limit to first 10 objects)
            for i, obj in enumerate(bpy.context.scene.objects):
                if i >= 10:  # Reduced from 20 to 10
                    break

                obj_info = {
                    "name": obj.name,
                    "type": obj.type,
                    # Only include basic location data
                    "location": [round(float(obj.location.x), 2),
                                round(float(obj.location.y), 2),
                                round(float(obj.location.z), 2)],
                }
                scene_info["objects"].append(obj_info)

            print(f"Scene info collected: {len(scene_info['objects'])} objects")
            return scene_info
        except Exception as e:
            print(f"Error in get_scene_info: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}

    @staticmethod
    def _get_aabb(obj):
        """ Returns the world-space axis-aligned bounding box (AABB) of an object. """
        if obj.type != 'MESH':
            raise TypeError("Object must be a mesh")

        # Get the bounding box corners in local space
        local_bbox_corners = [mathutils.Vector(corner) for corner in obj.bound_box]

        # Convert to world coordinates
        world_bbox_corners = [obj.matrix_world @ corner for corner in local_bbox_corners]

        # Compute axis-aligned min/max coordinates
        min_corner = mathutils.Vector(map(min, zip(*world_bbox_corners)))
        max_corner = mathutils.Vector(map(max, zip(*world_bbox_corners)))

        return [
            [*min_corner], [*max_corner]
        ]



    def get_object_info(self, name):
        """Get detailed information about a specific object"""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")

        # Basic object info
        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "location": [obj.location.x, obj.location.y, obj.location.z],
            "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            "visible": obj.visible_get(),
            "materials": [],
        }

        if obj.type == "MESH":
            bounding_box = self._get_aabb(obj)
            obj_info["world_bounding_box"] = bounding_box

        # Add material slots
        for slot in obj.material_slots:
            if slot.material:
                obj_info["materials"].append(slot.material.name)

        # Add mesh data if applicable
        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            obj_info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }

        return obj_info

    def get_viewport_screenshot(self, max_size=800, filepath=None, format="png"):
        """
        Capture a screenshot of the current 3D viewport and save it to the specified path.

        Parameters:
        - max_size: Maximum size in pixels for the largest dimension of the image
        - filepath: Path where to save the screenshot file
        - format: Image format (png, jpg, etc.)

        Returns success/error status
        """
        try:
            if not filepath:
                return {"error": "No filepath provided"}

            # Find the active 3D viewport
            area = None
            for a in bpy.context.screen.areas:
                if a.type == 'VIEW_3D':
                    area = a
                    break

            if not area:
                return {"error": "No 3D viewport found"}

            # Take screenshot with proper context override
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=filepath)

            # Load and resize if needed
            img = bpy.data.images.load(filepath)
            width, height = img.size

            if max(width, height) > max_size:
                scale = max_size / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img.scale(new_width, new_height)

                # Set format and save
                img.file_format = format.upper()
                img.save()
                width, height = new_width, new_height

            # Cleanup Blender image data
            bpy.data.images.remove(img)

            return {
                "success": True,
                "width": width,
                "height": height,
                "filepath": filepath
            }

        except Exception as e:
            return {"error": str(e)}

    def execute_code(self, code):
        """Execute arbitrary Blender Python code"""
        # This is powerful but potentially dangerous - use with caution
        try:
            # Create a local namespace for execution
            namespace = {"bpy": bpy}

            # Capture stdout during execution, and return it as result
            capture_buffer = io.StringIO()
            with redirect_stdout(capture_buffer):
                exec(code, namespace)

            captured_output = capture_buffer.getvalue()
            return {"executed": True, "result": captured_output}
        except Exception as e:
            raise Exception(f"Code execution error: {str(e)}")



    def get_polyhaven_categories(self, asset_type):
        """Get categories for a specific asset type from Polyhaven"""
        try:
            if asset_type not in ["hdris", "textures", "models", "all"]:
                return {"error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"}

            response = requests.get(f"https://api.polyhaven.com/categories/{asset_type}", headers=REQ_HEADERS)
            if response.status_code == 200:
                return {"categories": response.json()}
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def search_polyhaven_assets(self, asset_type=None, categories=None):
        """Search for assets from Polyhaven with optional filtering"""
        try:
            url = "https://api.polyhaven.com/assets"
            params = {}

            if asset_type and asset_type != "all":
                if asset_type not in ["hdris", "textures", "models"]:
                    return {"error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"}
                params["type"] = asset_type

            if categories:
                params["categories"] = categories

            response = requests.get(url, params=params, headers=REQ_HEADERS)
            if response.status_code == 200:
                # Limit the response size to avoid overwhelming Blender
                assets = response.json()
                # Return only the first 20 assets to keep response size manageable
                limited_assets = {}
                for i, (key, value) in enumerate(assets.items()):
                    if i >= 20:  # Limit to 20 assets
                        break
                    limited_assets[key] = value

                return {"assets": limited_assets, "total_count": len(assets), "returned_count": len(limited_assets)}
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def download_polyhaven_asset(self, asset_id, asset_type, resolution="1k", file_format=None):
        try:
            # First get the files information
            files_response = requests.get(f"https://api.polyhaven.com/files/{asset_id}", headers=REQ_HEADERS)
            if files_response.status_code != 200:
                return {"error": f"Failed to get asset files: {files_response.status_code}"}

            files_data = files_response.json()

            # Handle different asset types
            if asset_type == "hdris":
                # For HDRIs, download the .hdr or .exr file
                if not file_format:
                    file_format = "hdr"  # Default format for HDRIs

                if "hdri" in files_data and resolution in files_data["hdri"] and file_format in files_data["hdri"Пожалуйста, предоставьте `old_string` и `potentially_problematic_new_string` для анализа. I will then provide the corrected JSON output.```jsonjsonl{l