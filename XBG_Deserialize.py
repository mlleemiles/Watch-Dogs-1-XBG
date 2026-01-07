import BinaryReader

import json
from pathlib import Path
from enum import Enum

def vec2(r):
    return (r.f32(), r.f32())

def vec3(r):
    return (r.f32(), r.f32(), r.f32())

def sphere(r):
    return {
        "center": vec3(r),
        "radius": r.f32()
    }

def read_string_block(r, align=4):
    sid = r.u32()
    size = r.u32()
    value = r.string(size)
    r.align(align)
    return {"id": sid, "value": value}

class ESecondaryMotionObjectType(Enum):
    Cloth = 0
    Chain = 1
    Jiggle = 2

def read_header(r):
    return {
        "magic": r.u32(),
        "majorVersion": r.u16(),
        "minorVersion": r.u16(),
        "unk1": r.u32(),
        "unk2": r.u32(),
        "unk3": r.u32(),
    }

def read_memory_need(r):
    return {
        "total": r.u32(),
        "sceneMeshCount": r.u32()
    }

def read_unknown_params(r):
    out = {
        "unk1": r.f32(),
        "unk2": r.u8()
    }
    r.align(4)
    return out

def read_geom_params(r):
    out = {}

    out["meshDecompression"] = {
        "positionMin": r.f32(),
        "positionRange": r.f32()
    }

    out["uvDecompression"] = vec2(r)
    out["unk5"] = r.f32()
    out["unk6"] = r.f32()

    out["boundingSphere"] = sphere(r)
    out["bboxMin"] = vec3(r)
    out["bboxMax"] = vec3(r)

    out["unk11"] = r.u32()
    out["unk12"] = r.u32()
    out["unk13"] = r.u32()

    out["lodCount"] = r.u32()
    out["lodDistances"] = [r.f32() for _ in range(out["lodCount"])]

    out["killDistance"] = r.f32()
    out["castShadow"] = r.u8()
    out["showInReflection"] = r.u8()
    out["pcSkuLodFlags"] = r.u8()
    out["unk19"] = r.u8()

    out["firstLowEndLOD"] = r.u32()
    out["lowEndDistances"] = [
        r.f32() for _ in range(out["lodCount"] - out["firstLowEndLOD"])
    ]

    return out

def read_materials(r):
    out = {"materials": [], "slots": []}

    count = r.u32()
    for _ in range(count):
        out["materials"].append(read_string_block(r))

    slot_count = r.u32()
    for _ in range(slot_count):
        entry = read_string_block(r)
        entry["slotIndex"] = r.u32()
        out["slots"].append(entry)

    return out

def read_skins(r):
    skins = []
    count = r.u32()
    for _ in range(count):
        sid = r.u32()
        size = r.u32()
        name = r.string(size)
        r.align(4)
        skins.append({"id": sid, "name": name})
    return skins

def read_bone_palettes(r):
    palettes = []
    count = r.u32()
    for _ in range(count):
        bone_count = r.u32()
        indices = [r.u16() for _ in range(bone_count)]
        r.align(4)
        palettes.append(indices)
    r.align(4)
    return palettes

def read_skeletons(r):
    skels = []
    count = r.u32()
    for _ in range(count):
        nodes = []
        node_count = r.u32()
        for _ in range(node_count):
            boneLOD = r.u8()
            r.skip(3)
            pos = vec3(r)
            rot = [r.f32() for _ in range(4)]
            parent = r.u16()
            mat_idx = r.u16()
            nid = r.u32()
            size = r.u32()
            name = r.string(size)
            r.align(4)
            nodes.append({
                "boneLOD": boneLOD,
                "position": pos,
                "rotation": rot,
                "parent": parent,
                "matrixIndex": mat_idx,
                "id": nid,
                "name": name
            })
        skels.append(nodes)

    # object-to-bone matrices (raw)
    matrices = {
        "rootIndex": r.u32(),
        "count": r.u32(),
        "matrices": []
    }
    r.align(16)
    for _ in range(matrices["count"]):
        matrices["matrices"].append([r.f32() for _ in range(16)])

    return {"skeletons": skels, "objectToBone": matrices}

def read_reflex(r):
    has = r.u32()
    out = {"hasReflex": has}
    if has:
        size = r.u32()
        out["data"] = r.bytes(size)
        r.align(4)
    return out

def read_smos(r):
    secondary_motion_objects = []
    count = r.u32()
    for _ in range(1):
        simulation_parameters = {
            "gravity": vec3(r),
            "verticalStiffness": r.f32(),
            "horizontalStiffness": r.f32(),
            "shearStiffness": r.f32(),
            "bendStiffness": r.f32(),
            "viscousDrag": r.f32(),
            "aerodynamicDrag": r.f32(),
            "internalFriction": r.f32(),
            "jiggleStiffness": r.f32(),
            "frictionCoefficient": r.f32(),
            "frictionExtraRadius": r.f32(),
            "numIterations": r.u32(),
            "objectType": ESecondaryMotionObjectType(r.u32()),
            "useMaxLengthConstraints": r.u8()
        }
        r.align(4)

        collision_primitive_collection_description = {
            "spheres" : [],
            "cylinders" : [],
            "capsules" : [],
            "planes" : []
        }
        sphereCount = r.u32()
        collision_primitive_collection_description["sphereCount"] = sphereCount
        for _ in range(sphereCount):
            sphere = {
                "primitive" : read_string_block(r,16),
                "primitiveToBone": [],
            }
            sphere["primitiveToBone"].append([r.f32() for _ in range(16)])
            sphere["radius"] = r.f32()
            collision_primitive_collection_description["spheres"].append(sphere)

        cylinderCount = r.u32()
        collision_primitive_collection_description["cylinderCount"] = cylinderCount
        for _ in range(cylinderCount):
            cylinder = {
                "primitive" : read_string_block(r,16),
                "primitiveToBone": [],
            }
            cylinder["primitiveToBone"].append([r.f32() for _ in range(16)])
            cylinder["radius"] = r.f32()
            cylinder["localPointA"] = vec3(r)
            cylinder["localPointB"] = vec3(r)
            collision_primitive_collection_description["cylinders"].append(cylinder)

        capsuleCount = r.u32()
        collision_primitive_collection_description["capsuleCount"] = capsuleCount
        for _ in range(capsuleCount):
            capsule = {
                "primitive" : read_string_block(r,16),
                "primitiveToBone": [],
            }
            capsule["primitiveToBone"].append([r.f32() for _ in range(16)])
            capsule["radius"] = r.f32()
            capsule["localPointA"] = vec3(r)
            capsule["localPointB"] = vec3(r)
            collision_primitive_collection_description["capsules"].append(capsule)

        planeCount = r.u32()
        collision_primitive_collection_description["planeCount"] = planeCount
        for _ in range(planeCount):
            plane = {
                "primitive" : read_string_block(r,16),
                "primitiveToBone": [],
            }
            plane["primitiveToBone"].append([r.f32() for _ in range(16)])
            plane["localOrigin"] = vec3(r)
            plane["localNormal"] = vec3(r)
            collision_primitive_collection_description["planes"].append(plane)

        limit_collection_description = {
            "sphereLimits" : [],
            "boxLimits" : [],
            "cylinderLimits" : []
        }
        sphereLimitCount = r.u32()
        limit_collection_description["sphereLimitCount"] = sphereLimitCount
        for _ in range(sphereLimitCount):
            sphereLimit = {
                "primitive" : read_string_block(r,2),
                "particleIndex": r.u16(),
                "offset": vec3(r),
            }
            r.align(4)
            sphereLimit["radius"] = r.f32()
            limit_collection_description["sphereLimits"].append(sphereLimit)

        boxLimitCount = r.u32()
        limit_collection_description["boxLimitCount"] = boxLimitCount
        for _ in range(boxLimitCount):
            boxLimit = {
                "primitive" : read_string_block(r,2),
                "particleIndex": r.u16(),
                "offset": vec3(r),
            }
            r.align(4)
            boxLimit["halfRange"] = vec3(r)
            limit_collection_description["boxLimits"].append(boxLimit)

        cylinderLimitCount = r.u32()
        limit_collection_description["cylinderLimitCount"] = cylinderLimitCount
        for _ in range(cylinderLimitCount):
            cylinderLimit = {
                "primitive" : read_string_block(r,2),
                "particleIndex": r.u16(),
                "offset": vec3(r),
            }
            r.align(4)
            cylinderLimit["localDirection"] = vec3(r)
            cylinderLimit["length"] = r.f32()
            cylinderLimit["radius"] = r.f32()
            limit_collection_description["cylinderLimits"].append(cylinderLimit)

        particles = {
            "particle" : [],
        }
        particleCount = r.u32()
        particles["particleCount"] = particleCount
        for _ in range(particleCount):
            particle = {
                "name": read_string_block(r,4),
                "radius": r.f32(),
                "isAttached": r.u16(),
                "teleportParentBoneIndex": r.u16(),
                "texCoordinate": vec2(r)
            }
            particles["particle"].append(particle)

        teleport_parent_bones = {
            "teleportParentBones" : [],
        }
        boneCount = r.u32()
        teleport_parent_bones["boneCount"] = boneCount
        for _ in range(boneCount):
            teleport_parent_bone = {
                "name": read_string_block(r,4),
            }
            teleport_parent_bones["teleportParentBones"].append(teleport_parent_bone)

        secondary_motion_object = {
            "simulationParameters" : simulation_parameters,
            "collisionPrimitiveCollectionDescription" : collision_primitive_collection_description,
            "limitCollectionDescription" : limit_collection_description,
            "particles" : particles,
            "teleportParentBones" : teleport_parent_bones,
        }
        secondary_motion_objects.append(secondary_motion_object)

    return {"secondaryMotionObject": secondary_motion_objects}

def read_scene_meshes(r, lod_count):
    lods = []
    for _ in range(lod_count):
        meshes = []
        mesh_count = r.u32()
        for _ in range(mesh_count):
            meshes.append({
                "boundingSphere": sphere(r),
                "bboxMin": vec3(r),
                "bboxMax": vec3(r),
                "primitiveType": r.u32(),
                "materialIndex": r.u16(),
                "fvf": r.u16(),
                "vertexSize": r.u8(),
                "unk9": r.u8(),
                "unk10": r.u16(),
                "boneMapIndex": r.u32(),
            })
            # merged draw range
            #r.skip(32)
            range_count = r.u32()
            #r.skip(8)
            #for _ in range(range_count):
                #r.skip(96)
        lods.append(meshes)
    return lods


def read_buffers(r):
    bufs = []
    count = r.u32()
    for _ in range(count):
        vsize = r.u32()
        vbuf = r.bytes(vsize)
        r.align(4)
        isize = r.u32()
        ibuf = r.bytes(isize)
        r.align(4)
        bufs.append({
            "vertex": vbuf,
            "index": ibuf
        })
    return bufs

def read_mip(r):
    out = {"hasMips": r.u32()}
    if out["hasMips"]:
        out["unk1"] = r.u32()
        out["mipSize"] = r.u32()
        out["pathID"] = r.u32()
        size = r.u32()
        out["path"] = r.string(size)
        r.align(4)
    return out

def parse_geometry(path):
    data = Path(path).read_bytes()
    r = BinaryReader.BinaryReader(data)

    meta = {}
    meta["header"] = read_header(r)
    meta["memory"] = read_memory_need(r)
    meta["unknown"] = read_unknown_params(r)
    meta["geomParams"] = read_geom_params(r)
    meta["materials"] = read_materials(r)
    meta["skins"] = read_skins(r)
    meta["bonePalettes"] = read_bone_palettes(r)
    meta["skeletons"] = read_skeletons(r)
    meta["reflex"] = read_reflex(r)
    meta["secondaryMotionObjects"] = read_smos(r)

    # raw_start = r.tell()
    #meta["rawBetween"] = r.bytes(len(data) - r.tell())
    #meta["fileSize"] = len(data)

    return meta

parse_geometry(r".\char01.xbg")

