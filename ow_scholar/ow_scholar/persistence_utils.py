
__all__ = ['vol', 'volprop']


def vol(obj, name, thunk):
    if not hasattr(obj, name):
        setattr(obj, name, thunk())
    return getattr(obj, name)


def volprop(name, thunk=lambda: None, setter=True):
    volname = '_v_' + name

    def gf(self):
        return vol(self, volname, thunk)

    prop = property(gf)
    if setter:
        def sf(self, v):
            setattr(self, volname, v)
        prop = prop.setter(sf)
    return prop
