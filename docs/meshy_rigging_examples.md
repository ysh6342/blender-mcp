# Meshy Rigging Examples

This document provides examples of how to use the new rigging MCP tools to process humanoid characters, particularly those from Meshy AI, and prepare them for Unreal Engine 5.

## Example 1: Meshy Character (Mesh-Only)

This workflow takes a character that is just a mesh with no armature and performs a full auto-rig, adds fingers, renames the bones for UE5, and exports an FBX.

### 1. Inspect the Character

First, check the character to confirm it's a mesh-only model.

```
inspect_humanoid_rig
```

**Expected Output:**
A JSON response indicating `"rig_type": "mesh_only"`.

### 2. Auto-Rig the Character

Since there is no armature, use the `auto_rig_meshy_character` tool. This will create a basic skeleton and apply automatic weights.

```
auto_rig_meshy_character
```

**Expected Output:**
A JSON response confirming the creation of a new armature, e.g., `"status": "success"`.

### 3. Ensure Finger Chains

The basic auto-rigger may not create fingers. Use `ensure_finger_chains_for_hand` for both hands.

```
ensure_finger_chains_for_hand side="L"
ensure_finger_chains_for_hand side="R"
```

### 4. Rename Bones for UE5

Convert the bone names to the UE5 Mannequin standard. We'll do a dry run first.

```
rename_fingers_to_ue5 dry_run=True
```

If the proposed mapping looks correct, execute the renaming.

```
rename_fingers_to_ue5 dry_run=False
```

### 5. Export the FBX

Finally, export the UE5-ready character.

```
export_ue5_ready_fbx filepath="C:/Users/YourUser/Desktop/MyCharacter.fbx"
```

---

## Example 2: Meshy Character with Existing Mixamo Armature

This workflow handles a character that has already been processed by Mixamo. The goal is to fix the finger rigging and rename the bones correctly for UE5.

### 1. Inspect the Character

Check the character to confirm it has a Mixamo-style rig.

```
inspect_humanoid_rig
```

**Expected Output:**
A JSON response indicating `"rig_type": "mixamo"`.

### 2. Add or Fix Finger Rigging

Mixamo rigs often have poor finger rigs. Use the `arp_add_or_fix_finger_rig` tool. If Auto-Rig Pro is installed, it will use its superior finger rigging. If not, it will fall back to the `ensure_finger_chains_for_hand` and `auto_weight_fingers_only` tools.

```
arp_add_or_fix_finger_rig side="both"
```

### 3. Rename Bones for UE5

The bone names will be in the Mixamo format (e.g., `mixamorig:LeftHand`). Convert them to the UE5 standard.

```
rename_fingers_to_ue5 dry_run=False include_body=True
```
*Note: `include_body=True` is used here to rename the Mixamo body bones as well.*

### 4. Export the FBX

Export the final, UE5-ready character.

```
export_ue5_ready_fbx filepath="C:/Users/YourUser/Desktop/MyMixamoCharacter_UE5.fbx"
```
