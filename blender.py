import sys
import bpy
import bmesh
import struct
import os  # For safe path handling

# Add your XBG parser path
sys.path.append(r"C:\Users\mllee\PycharmProjects\XBG_Deserialize")
import BinaryReader
from XBGParser import XBGParser


# --------------------------
# Helper Functions
# --------------------------
def create_empty_parent(name, parent_obj=None, loc=(0, 0, 0)):
    """Create empty object with safe parenting"""
    empty = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(empty)
    empty.location = loc
    if parent_obj:
        empty.parent = parent_obj
    return empty


def reset_reader(reader, buffer_data):
    """Reset binary reader to start of buffer (critical for multi-LOD)"""
    reader.set_buffer(buffer_data)
    reader.seek(0)


def prune_unused_vertices(bm):
    """Remove unused vertices from a BMesh (vertices with no face/edge connections)"""
    # Collect vertices with no edges/faces
    unused_verts = [v for v in bm.verts if not v.link_faces and not v.link_edges]
    # Delete unused vertices
    for v in unused_verts:
        bm.verts.remove(v)
    # Update BMesh to apply changes
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


# --------------------------
# 1. Parse XBG File
# --------------------------
xbg_path = r"D:\Steam\steamapps\common\Watch_Dogs\data_win64\worlds\windy_city\windy_city_unpack\graphics\characters\char\char01\char01_torso.xbg"
xbg_name = os.path.splitext(os.path.basename(xbg_path))[0]
parser = XBGParser(xbg_path)
meta_data = parser.parse()

# Extract filename safely (fix for f-string backslash error)
xbg_filename = os.path.basename(xbg_path).split('.')[0]

# Critical metadata
lod_count = meta_data["geomParams"]["lodCount"]
buffers = meta_data["buffers"]["gfxBuffer"]
lod_distances = meta_data["geomParams"]["lodDistances"] if lod_count > 0 else []
pos_min = meta_data["geomParams"]["meshDecompression"]["positionMin"]
pos_range = meta_data["geomParams"]["meshDecompression"]["positionRange"]

print(f"=== XBG Import Debug ===")
print(f"File: {xbg_filename}")
print(f"Total LODs: {lod_count}")
print(f"Total Buffers: {len(buffers)}")
print(f"LOD Distances: {lod_distances}")
print(f"========================")

# Validate core data
if lod_count == 0:
    raise Exception("No LODs found in XBG file!")
if len(buffers) == 0:
    raise Exception("No vertex/index buffers found!")

# --------------------------
# 2. Clear Default Objects
# --------------------------
for obj in bpy.data.objects:
    obj.hide_set(False)  # Make visible in viewport
    obj.hide_select = False  # Make selectable

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# --------------------------
# 3. Create Root Hierarchy
# --------------------------
root_empty = create_empty_parent(f"{xbg_filename}")
root_empty.location = (0, 0, 0)

# --------------------------
# 4. Process ALL LODs (With Shared Vertex Grouping)
# --------------------------
global_submesh_id = 0

for lod_index in range(lod_count):
    # --------------------------
    # A. Create LOD Parent Empty
    # --------------------------
    lod_name = f"LOD{lod_index}"
    lod_parent = create_empty_parent(lod_name, parent_obj=root_empty)
    # lod_parent.hide_viewport = lod_index != 0  # Hide all except LOD 0
    # lod_parent.hide_render = lod_index != 0

    # --------------------------
    # B. Get LOD-Specific Buffer & Data
    # --------------------------
    buffer_idx = min(lod_index, len(buffers) - 1)
    current_buffer = buffers[buffer_idx]
    vertex_buffer = current_buffer["vertexBuffer"]
    index_buffer = current_buffer["indexBuffer"]

    # Reset readers for THIS LOD (critical!)
    vertex_reader = BinaryReader.BinaryReader(vertex_buffer)
    index_reader = BinaryReader.BinaryReader(index_buffer)
    reset_reader(vertex_reader, vertex_buffer)
    reset_reader(index_reader, index_buffer)

    # Validate LOD mesh data
    if lod_index >= len(meta_data["meshes"]):
        print(f"Warning: No meshes found for LOD {lod_index}")
        continue
    lod_meshes = meta_data["meshes"][lod_index]

    # --------------------------
    # C. Group Meshes by SHARED Vertex Stream (Your Original Logic)
    # --------------------------
    vertex_groups = {}  # Key: (vertex_offset, vertex_count), Value: group data
    group_order = []

    for submesh_idx, scene_mesh in enumerate(lod_meshes):
        mr = scene_mesh["mergedRanges"]
        # Key = unique identifier for shared vertex stream
        group_key = (mr["vertexBufferByteOffset"], mr["vertexCount"])

        # Create new group if it doesn't exist
        if group_key not in vertex_groups:
            vertex_groups[group_key] = {
                "vertex_offset": mr["vertexBufferByteOffset"],
                "vertex_count": mr["vertexCount"],
                "vertex_size": scene_mesh["vertexSize"],
                "primitive_type": scene_mesh["primitiveType"],
                "submeshes": []  # Store submeshes that share this vertex stream
            }
            group_order.append(group_key)

        # Add submesh to the group (with its draw ranges)
        vertex_groups[group_key]["submeshes"].append({
            "submesh_idx": submesh_idx,
            "mat_index": scene_mesh["materialIndex"],
            "draw_ranges": scene_mesh["ranges"]
        })

    # --------------------------
    # D. Process Each Shared Vertex Group
    # --------------------------
    for group_idx, group_key in enumerate(group_order):
        group = vertex_groups[group_key]
        vertex_offset = group["vertex_offset"]
        vertex_count = group["vertex_count"]
        vertex_size = group["vertex_size"]
        primitive_type = group["primitive_type"]

        # Skip invalid groups
        if vertex_count == 0 or vertex_size < 6:
            print(f"LOD {lod_index}: Skipping invalid vertex group {group_idx}")
            continue

        # --------------------------
        # E. Read SHARED Vertex Stream ONCE for the group
        # --------------------------
        reset_reader(vertex_reader, vertex_buffer)
        vertex_reader.seek(vertex_offset)
        positions = []

        for _ in range(vertex_count):
            # Read and decompress 16-bit vertex coordinates
            x = vertex_reader.i16() * pos_range + pos_min
            y = vertex_reader.i16() * pos_range + pos_min
            z = vertex_reader.i16() * pos_range + pos_min
            positions.append((x, y, z))

            # Skip remaining vertex bytes (safe skip)
            vertex_reader.skip(max(0, vertex_size - 6))

        # --------------------------
        # F. Create Group Parent Empty
        # --------------------------
        group_parent = create_empty_parent(
            f"Vertex_Group_{group_idx}",
            parent_obj=lod_parent
        )

        # --------------------------
        # G. Process All Submeshes in This Group
        # --------------------------
        for submesh_data in group["submeshes"]:
            submesh_idx = submesh_data["submesh_idx"]
            mat_index = submesh_data["mat_index"]
            draw_ranges = submesh_data["draw_ranges"]

            material_slot_index = lod_meshes[submesh_idx]["materialIndex"]
            for slot_index, slot in enumerate(meta_data["materials"]["slots"]):
                if slot["slotIndex"] == material_slot_index:
                    material_slot_name = slot["value"]
                    break

            # Create Submesh Parent Empty
            submesh_parent = create_empty_parent(
                f"{material_slot_name}",
                parent_obj=group_parent
            )

            # --------------------------
            # H. Process Each Draw Range in the Submesh
            # --------------------------
            for range_idx, draw_range in enumerate(draw_ranges):
                dc = draw_range["drawCall"]
                idx_offset = dc["indexBufferStartIndex"] * 2  # 16-bit indices
                idx_count = dc["indexCount"]

                if idx_count == 0:
                    continue

                # --------------------------
                # I. Create BMesh (Reuse Shared Vertices)
                # --------------------------
                bm = bmesh.new()
                # Add shared vertices ONCE (reused across all submeshes in the group)
                bm_verts = [bm.verts.new(pos) for pos in positions]
                bm.verts.ensure_lookup_table()

                # --------------------------
                # J. Read Indices & Create Faces
                # --------------------------
                reset_reader(index_reader, index_buffer)
                index_reader.seek(idx_offset)

                try:
                    if primitive_type.name == "TriangleList":
                        # Triangle list: 3 indices per face
                        for _ in range(idx_count // 3):
                            a = index_reader.u16()
                            b = index_reader.u16()
                            c = index_reader.u16()
                            if 0 <= a < len(bm_verts) and 0 <= b < len(bm_verts) and 0 <= c < len(bm_verts):
                                bm.faces.new([bm_verts[a], bm_verts[b], bm_verts[c]])

                    elif primitive_type.name == "TriangleStrip":
                        # Triangle strip: convert to triangle list
                        indices = [index_reader.u16() for _ in range(idx_count)]
                        for i in range(2, len(indices)):
                            if i % 2 == 0:
                                a, b, c = indices[i - 2], indices[i - 1], indices[i]
                            else:
                                a, b, c = indices[i - 1], indices[i - 2], indices[i]
                            if 0 <= a < len(bm_verts) and 0 <= b < len(bm_verts) and 0 <= c < len(bm_verts):
                                bm.faces.new([bm_verts[a], bm_verts[b], bm_verts[c]])

                    bm = prune_unused_vertices(bm)

                except Exception as e:
                    print(f"LOD {lod_index} Group {group_idx} Range {range_idx}: Error - {e}")
                    bm.free()
                    continue

                # --------------------------
                # K. Create Blender Mesh Object
                # --------------------------
                skin_name = lod_meshes[submesh_idx]["ranges"][range_idx]["name"]["value"]
                mesh_name = f"{skin_name}"
                mesh_data = bpy.data.meshes.new(mesh_name)
                bm.to_mesh(mesh_data)
                bm.free()

                # Link to scene and parent to submesh empty
                mesh_obj = bpy.data.objects.new(mesh_name, mesh_data)
                bpy.context.collection.objects.link(mesh_obj)
                mesh_obj.parent = submesh_parent

                # Add custom properties
                mesh_obj["lod_index"] = lod_index
                mesh_obj["vertex_group_idx"] = group_idx
                mesh_obj["submesh_idx"] = submesh_idx
                mesh_obj["material_index"] = mat_index
                mesh_obj["skin_index"] = draw_range["skinIndex"]
                if lod_index < len(lod_distances):
                    mesh_obj["lod_switch_distance"] = lod_distances[lod_index]

                global_submesh_id += 1

# --------------------------
# Final Output
# --------------------------
print(f"\n✅ Import Complete!")
print(f"- Total submeshes created: {global_submesh_id}")
print(f"- Root object: {root_empty.name}")
print(f"- Toggle LOD visibility in the Outliner (eye icon)")