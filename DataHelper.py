def vec2(r):
    return r.f32(), r.f32()

def vec3(r):
    return r.f32(), r.f32(), r.f32()

def sphere(r):
    return {
        "center": vec3(r),
        "radius": r.f32()
    }