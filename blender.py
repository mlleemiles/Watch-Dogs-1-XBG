import sys
import bpy
import bmesh
import os

# Add XBG parser path
sys.path.append(r"C:\Users\mllee\PycharmProjects\XBG_Deserialize")
import BinaryReader
from XBGParser import XBGParser


# --------------------------
# Core Helper Functions (No Nesting)
# --------------------------
def create_collection(name, parent_collection=None):
    """Create and link a Blender Collection"""
    new_col = bpy.data.collections.new(name)
    if parent_collection:
        parent_collection.children.link(new_col)
    else:
        bpy.context.scene.collection.children.link(new_col)
    return new_col


def reset_reader(reader, buffer_data):
    """Reset binary reader to start of buffer"""
    reader.set_buffer(buffer_data)
    reader.seek(0)


def prune_unused_vertices(bm):
    """Remove unused vertices from BMesh"""
    unused_verts = [v for v in bm.verts if not v.link_faces and not v.link_edges]
    for v in unused_verts:
        bm.verts.remove(v)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def full_cleanup():
    """Clear all objects and non-default collections"""
    # Delete all objects
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)
    # Delete non-default collections
    default_collections = {"Collection"}
    for col in bpy.data.collections:
        if col.name not in default_collections:
            bpy.data.collections.remove(col)


def precompute_bone_mapping(xbg_data):
    """Precompute bone index mapping to avoid repeated lookups (MAJOR OPTIMIZATION)"""
    bone_mapping = []
    if not xbg_data.get("skeletons") or not xbg_data["skeletons"].get("skeletons"):
        return bone_mapping

    skeleton = xbg_data["skeletons"]["skeletons"][0]
    if len(xbg_data["bonePalettes"]) > 0:
        for _ in range(len(xbg_data["bonePalettes"])):
            bone_map_reorder = {}
            for bone_id, bone_data in enumerate(skeleton):
                matrix_index = bone_data["matrixIndex"]
                bone_map_reorder[matrix_index] = bone_id

            bone_mapping.append(bone_map_reorder)
    else:
        bone_map_reorder = {}
        for bone_id, bone_data in enumerate(skeleton):
            matrix_index = bone_data["matrixIndex"]
            bone_map_reorder[matrix_index] = bone_id
        bone_mapping.append(bone_map_reorder)

    return bone_mapping


def read_vertex_data(vertex_reader, vertex_buffer, mesh, pos_min, pos_range, uv_decomp_xy, uv_decomp_zw):
    """Read vertex positions and UVs (single-purpose function) - FIXED: Pass vertex_buffer explicitly"""

    vertex_offset = mesh["mergedRanges"]["vertexBufferByteOffset"]
    vertex_count = mesh["mergedRanges"]["vertexCount"]
    vertex_size = mesh["vertexSize"]

    reset_reader(vertex_reader, vertex_buffer)  # Fixed: Use passed vertex_buffer instead of reader.buffer
    vertex_reader.seek(vertex_offset)

    positions = []
    uv0 = []
    uv1 = []
    bone_indices = []
    bone_weights = []

    for _ in range(vertex_count):
        read_bytes = 0
        # Read position (skip w component)
        if mesh["PointComp"]:
            x = vertex_reader.i16() * pos_range + pos_min
            y = vertex_reader.i16() * pos_range + pos_min
            z = vertex_reader.i16() * pos_range + pos_min
            vertex_reader.i16()  # Skip w
            positions.append((x, y, z))
            read_bytes += 8

        # UV needs wrap address mode, dunno why
        # Flipped V because blender is fucking stupid
        # Read UV0
        if mesh["UVComp1"]:
            uv0_u = (vertex_reader.i16() * uv_decomp_zw + uv_decomp_xy) % 1.0
            uv0_v = (-vertex_reader.i16() * uv_decomp_zw + uv_decomp_xy) % 1.0
            uv0.append((uv0_u, uv0_v))
            read_bytes += 4

        # Read UV1
        if mesh["UVComp2"]:
            uv1_u = (vertex_reader.i16() * uv_decomp_zw + uv_decomp_xy) % 1.0
            uv1_v = (-vertex_reader.i16() * uv_decomp_zw + uv_decomp_xy) % 1.0
            uv1.append((uv1_u, uv1_v))
            read_bytes += 4

        if mesh["Skin"]:
            w0 = vertex_reader.u8() / 255.0
            w1 = vertex_reader.u8() / 255.0
            w2 = vertex_reader.u8() / 255.0
            w3 = vertex_reader.u8() / 255.0

            b0 = vertex_reader.u8()
            b1 = vertex_reader.u8()
            b2 = vertex_reader.u8()
            b3 = vertex_reader.u8()
            read_bytes += 8

            if mesh["SkinExtra"]:
                w4 = vertex_reader.u8() / 255.0
                w5 = vertex_reader.u8() / 255.0
                b4 = vertex_reader.u8()
                b5 = vertex_reader.u8()
                read_bytes += 4
                bone_indices.append((b0, b1, b2, b3, b4, b5))
                bone_weights.append((w0, w1, w2, w3, w4, w5))
            else:
                bone_indices.append((b0, b1, b2, b3))
                bone_weights.append((w0, w1, w2, w3))

        vertex_reader.skip(vertex_size - read_bytes)

    # Prepare UV sets for return
    uv_sets = []
    uv_set_names = []
    if mesh["UVComp1"]:
        uv_sets.append(uv0)
        uv_set_names.append("uv0")
    if mesh["UVComp2"]:
        uv_sets.append(uv1)
        uv_set_names.append("uv1")

    return positions, uv_sets, uv_set_names, bone_indices, bone_weights


def read_indices(index_reader, index_buffer, idx_offset, idx_count, primitive_type):
    """Read index data (single-purpose function)"""
    reset_reader(index_reader, index_buffer)  # Uses passed index_buffer (correct)
    index_reader.seek(idx_offset)

    indices_list = []

    if primitive_type.name == "TriangleList":
        for _ in range(idx_count // 3):
            a, b, c = index_reader.u16(), index_reader.u16(), index_reader.u16()
            indices_list.append((a, b, c))
    elif primitive_type.name == "TriangleStrip":
        indices = [index_reader.u16() for _ in range(idx_count)]
        for i in range(2, len(indices)):
            if i % 2 == 0:
                a, b, c = indices[i - 2], indices[i - 1], indices[i]
            else:
                a, b, c = indices[i - 1], indices[i - 2], indices[i]
            indices_list.append((a, b, c))

    return indices_list


def create_mesh_object(positions, mesh, xbg, bone_mapping, indices_list, uv_sets, uv_set_names, skin_name, bone_indices, bone_weights):
    """Create Blender mesh object (single-purpose function)"""
    # Create BMesh
    bm = bmesh.new()

    # Add UV layers
    uv_layers = [bm.loops.layers.uv.new(name) for name in uv_set_names]

    # Create vertices
    bm_verts = [bm.verts.new(pos) for pos in positions]
    bm.verts.ensure_lookup_table()

    # Create faces and assign UVs
    for a_idx, b_idx, c_idx in indices_list:
        a, b, c = bm_verts[a_idx], bm_verts[b_idx], bm_verts[c_idx]
        face = bm.faces.new([a, b, c])
        if mesh["UVComp1"] or mesh["UV"]:
            # Assign UVs to face loops
            for uv_set_idx, uv_layer in enumerate(uv_layers):
                uv_list = uv_sets[uv_set_idx]
                face.loops[0][uv_layer].uv = uv_list[a_idx]
                face.loops[1][uv_layer].uv = uv_list[b_idx]
                face.loops[2][uv_layer].uv = uv_list[c_idx]

    # Prune unused vertices
    # bm = prune_unused_vertices(bm)

    # Create mesh data and object
    mesh_data = bpy.data.meshes.new(skin_name)
    bm.to_mesh(mesh_data)
    # bm.free()

    mesh_obj = bpy.data.objects.new(skin_name, mesh_data)

    if mesh["Skin"]:
        bone_count = 4
        if mesh["SkinExtra"]:
            bone_count = 6
        for i in range(mesh["mergedRanges"]["minIndexValue"], mesh["mergedRanges"]["maxIndexValue"] + 1):
            for j in range(bone_count):
                if bone_weights[i][j] != 0.0:
                    if mesh["boneMapIndex"] == 0xFFFFFFFF:
                        boneIndex = bone_indices[i][j]
                        boneIndex = bone_mapping[0][boneIndex]
                        vertex_group_name = xbg["skeletons"]["skeletons"][0][boneIndex]["name"]
                    else:
                        boneMap = xbg["bonePalettes"][mesh["boneMapIndex"]]
                        #print(f"Bone Map Index: {len(boneMap)} {mesh['boneMapIndex']} Bone Index: {bone_indices[i][j]} {i}")
                        #print(f"Mesh material: {mesh['materialIndex']}")
                        boneIndex = boneMap[bone_indices[i][j]]
                        boneIndex = bone_mapping[mesh["boneMapIndex"]][boneIndex]
                        vertex_group_name = xbg["skeletons"]["skeletons"][0][boneIndex]["name"]

                    if vertex_group_name not in mesh_obj.vertex_groups:
                        mesh_obj.vertex_groups.new(name=vertex_group_name)
                    else:
                        mesh_obj.vertex_groups[vertex_group_name]

                    mesh_obj.vertex_groups[vertex_group_name].add([i], bone_weights[i][j], 'ADD')


    #bm.free()

    bm.from_mesh(mesh_obj.data)
    bm = prune_unused_vertices(bm)
    bm.to_mesh(mesh_obj.data)
    bm.free()



    return mesh_obj


def get_material_name(meta_data, lod_meshes, submesh_idx, mat_index):
    """Get material slot name (single-purpose function)"""
    material_slot_name = f"Material_{mat_index}"
    material_slot_index = lod_meshes[submesh_idx]["materialIndex"]
    for slot in meta_data["materials"]["slots"]:
        if slot["slotIndex"] == material_slot_index:
            material_slot_name = slot["value"]
            break
    return material_slot_name


# --------------------------
# Main Import Logic (Flat Loop Hierarchy)
# --------------------------
def import_xbg(xbg_path):
    # Parse XBG file
    xbg_name = os.path.splitext(os.path.basename(xbg_path))[0]
    parser = XBGParser(xbg_path)
    meta_data = parser.parse()

    # Extract core metadata
    lod_count = meta_data["geomParams"]["lodCount"]
    buffers = meta_data["buffers"]["gfxBuffer"]
    lod_distances = meta_data["geomParams"]["lodDistances"]
    pos_min = meta_data["geomParams"]["meshDecompression"]["positionMin"]
    pos_range = meta_data["geomParams"]["meshDecompression"]["positionRange"]
    uv_decomp_xy = meta_data["geomParams"]["uvDecompression"]["UVDecompressionXY"]
    uv_decomp_zw = meta_data["geomParams"]["uvDecompression"]["UVDecompressionZW"]

    bone_mapping = precompute_bone_mapping(meta_data)

    # Print basic info
    print(f"=== XBG Import ===")
    print(f"File: {xbg_name}")
    print(f"Total LODs: {lod_count}")
    print(f"Total Buffers: {len(buffers)}")
    print(f"==================")

    # Clean slate
    full_cleanup()

    # Create root collection
    root_collection = create_collection(xbg_name)

    # Track progress
    global_submesh_id = 0

    # --------------------------
    # Process LODs (Level 1 Loop)
    # --------------------------
    for lod_index in range(lod_count):
        # Create LOD collection
        lod_collection = create_collection(f"LOD{lod_index}", root_collection)

        # Get LOD buffer data
        buffer_idx = min(lod_index, len(buffers) - 1)
        current_buffer = buffers[buffer_idx]
        vertex_buffer = current_buffer["vertexBuffer"]  # This is the raw buffer data
        index_buffer = current_buffer["indexBuffer"]  # This is the raw buffer data

        # Initialize readers
        vertex_reader = BinaryReader.BinaryReader(vertex_buffer)
        index_reader = BinaryReader.BinaryReader(index_buffer)

        # Get LOD meshes
        lod_meshes = meta_data["meshes"][lod_index]

        # --------------------------
        # Group meshes by shared vertex stream (Helper Logic)
        # --------------------------
        vertex_groups = {}
        group_order = []
        for submesh_idx, scene_mesh in enumerate(lod_meshes):
            mr = scene_mesh["mergedRanges"]
            group_key = (mr["vertexBufferByteOffset"], mr["vertexCount"])

            if group_key not in vertex_groups:
                vertex_groups[group_key] = {
                    "vertex_offset": mr["vertexBufferByteOffset"],
                    "vertex_count": mr["vertexCount"],
                    "vertex_size": scene_mesh["vertexSize"],
                    "primitive_type": scene_mesh["primitiveType"],
                    "submeshes": []
                }
                group_order.append(group_key)

            vertex_groups[group_key]["submeshes"].append({
                "submesh_idx": submesh_idx,
                "mat_index": scene_mesh["materialIndex"],
                "draw_ranges": scene_mesh["ranges"]
            })

        # --------------------------
        # Process vertex groups (Level 2 Loop)
        # --------------------------
        for group_idx, group_key in enumerate(group_order):
            group = vertex_groups[group_key]
            primitive_type = group["primitive_type"]

            # Create vertex group collection
            group_collection = create_collection(f"Vertex_Group_{group_idx}", lod_collection)
            mesh = lod_meshes[group["submeshes"][0]["submesh_idx"]]

            # Read vertex data (FIXED: Pass vertex_buffer explicitly)
            positions, uv_sets, uv_set_names, bone_indices, bone_weights= read_vertex_data(
                vertex_reader, vertex_buffer, mesh, pos_min, pos_range, uv_decomp_xy, uv_decomp_zw
            )

            # --------------------------
            # Process submeshes (Level 3 Loop)
            # --------------------------
            for submesh_data in group["submeshes"]:
                submesh_idx = submesh_data["submesh_idx"]
                mat_index = submesh_data["mat_index"]
                draw_ranges = submesh_data["draw_ranges"]

                # Get material name (DELEGATED TO FUNCTION)
                material_slot_name = get_material_name(meta_data, lod_meshes, submesh_idx, mat_index)

                # Create submesh collection
                submesh_collection = create_collection(material_slot_name, group_collection)

                # --------------------------
                # Process draw ranges (Level 4 Loop)
                # --------------------------
                for range_idx, draw_range in enumerate(draw_ranges):
                    dc = draw_range["drawCall"]
                    idx_offset = dc["indexBufferStartIndex"] * 2
                    idx_count = dc["indexCount"]

                    # Read indices (DELEGATED TO FUNCTION)
                    indices_list = read_indices(
                        index_reader, index_buffer, idx_offset, idx_count, primitive_type
                    )

                    # Create mesh object (DELEGATED TO FUNCTION)
                    skin_name = lod_meshes[submesh_idx]["ranges"][range_idx]["name"]["value"]
                    mesh_obj = create_mesh_object(
                        positions, lod_meshes[submesh_idx], meta_data, bone_mapping, indices_list, uv_sets, uv_set_names, skin_name, bone_indices, bone_weights
                    )

                    # Link to collection
                    if mesh_obj.name in bpy.context.scene.collection.objects:
                        bpy.context.scene.collection.objects.unlink(mesh_obj)
                    submesh_collection.objects.link(mesh_obj)

                    # Add custom properties
                    # mesh_obj["lod_index"] = lod_index
                    # mesh_obj["vertex_group_idx"] = group_idx
                    # mesh_obj["submesh_idx"] = submesh_idx
                    # mesh_obj["material_index"] = mat_index
                    # mesh_obj["skin_index"] = draw_range["skinIndex"]
                    # mesh_obj["original_vertex_count"] = len(positions)
                    # mesh_obj["used_vertex_count"] = len(used_indices)
                    # if lod_index < len(lod_distances):
                        # mesh_obj["lod_switch_distance"] = lod_distances[lod_index]

                    # Print progress
                    print(
                        f"LOD {lod_index} Range {range_idx}: Pruned {len(positions) - len(indices_list)} unused vertices")
                    global_submesh_id += 1

    # Final output
    print(f"\n✅ Import Complete!")
    print(f"- Total submeshes created: {global_submesh_id}")
    print(f"- Root collection: {root_collection.name}")


# --------------------------
# Run the Import
# --------------------------
if __name__ == "__main__":
    XBG_PATH = r"D:\Steam\steamapps\common\Watch_Dogs\data_win64\worlds\windy_city\windy_city_unpack\graphics\characters\char\char01\char01.xbg"
    import_xbg(XBG_PATH)