from math import log, exp, sqrt
from functools import wraps

from zope.interface import *


###############################################################################
# Utility functions
###############################################################################

def memoized(func):
    ''' Caches the results of a function '''
    cache = {}

    @wraps(func)
    def new_fn(*args, **kwargs):
        key = (args, str(kwargs))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    return new_fn

###############################################################################
# Interfaces
###############################################################################

class IComponent(Interface):
    ''' Basic rocket component '''
    
    mass = Attribute('''Component mass''')
    drag = Attribute('''Coefficient of drag''')


class IParachute(IComponent):
    ''' Basic rocket component '''
    
    drag_stowed = Attribute('''Coefficient of drag, stowed''')
    drag_deployed = Attribute('''Coefficient of drag, deployed''')

    def deploy(self):
        ''' Deploy the chute, changing drag '''

    def stow(self):
        ''' Stow the chute, changing drag '''


class ITank(IComponent):
    ''' Rocket component holding fuel '''
    
    mass_fuel = Attribute('''Mass of the carried fuel''')


class IEngine(IComponent):
    ''' Rocket component holding fuel '''
    
    thrust = Attribute('''Engine thrust''')
    isp_atm = Attribute('''Engine Isp at 1 atm''')
    isp_vac = Attribute('''Engine Isp at 0 atm''')


class IPlanet(Interface):
    ''' Planetary information '''

    gravity = Attribute('''Surface gravity''')
    dv_out = Attribute('''delta-v needed to escape atmosphere''')
    dv_escape = Attribute('''delta-v needed to escape the planet''')


###############################################################################
# Planets
###############################################################################

class Atmosphere(object):

    def __init__(self, pressure, height):
        self._pressure = pressure # At altitude 0, in atm
        self._height = height # scale height in m

    def pressure(self, altitude):
        if altitude > self.height:
            return 0.0
        return self._pressure * exp(-altitude / self._height)

    @property
    def scale_height(self):
        return self._height

    @property
    @memoized
    def height(self):
        ''' Height at which the atmosphere ends '''
        return -log(1.0e-6 / self._pressure) * self._height

    @memoized
    def __str__(self):
        info = [
            '  Atmosphere info', '\n',
            '    pressure (sea level) : ', str(self._pressure), '\n',
            '    atmosphere height    : ', str(self.height), '\n',
            '    scale height         : ', str(self._height),
        ]
        return ''.join(info)
        

@implementer(IPlanet)
class Planet(object):
    ''' Planetary information '''

    def __init__(self, name, mass, radius, atmosphere=None):
        self.name = name
        self.mass = mass
        self.radius = radius # Equatorial
        self.atmosphere = atmosphere

    @property
    @memoized
    def gravity(self):
        return self.g_force(0, 1)

    def g_force(self, altitude, mass):
        distance = self.radius + altitude
        return 6.6725985e-11 * mass * self.mass / (distance**2)

    def d_force(self, altitude, velocity, mass, drag):
        if self.atmosphere is None:
            return 0.0
        rho = self.atmosphere.pressure(altitude) * 1.2230948554874
        area = 0.008 * mass # Weird KSP approximation
        return 0.5 * rho * velocity**2 * area * drag

    def terminal_velocity(self, altitude, drag):
        if self.atmosphere is None:
            return float("inf")
        rho = self.atmosphere.pressure(altitude) * 1.2230948554874
        return sqrt(self.g_force(altitude, 250) / (rho * drag))

    # @property
    # def dv_out(self):
    #     return self._dv_out

    # @property
    # def dv_escape(self):
    #     return self._dv_escape

    @memoized
    def __str__(self):
        info = [
            'Planetary info for ', self.name, '\n',
            '  mass              : ', str(self.mass), '\n',
            '  equatorial radius : ', str(self.radius), '\n',
            '  surface gravity   : ', str(self.gravity), '\n',
        ]
        if self.atmosphere is None:
            info.append('  No atmosphere')
        else:
            info.append(str(self.atmosphere))
        return ''.join(info)


Kerbin = Planet('Kerbin', 5.2915793e22, 600000, Atmosphere(1, 5000))


###############################################################################
# Rockets
###############################################################################

@implementer(IComponent)
class Component(object):
    ''' Stupid extra mass '''

    def __init__(self, mass, drag):
        self._mass = float(mass)
        self._drag = float(drag)

    @property
    def mass(self):
        return self._mass

    @property
    def drag(self):
        return self._drag


@implementer(IParachute)
class Parachute(Component):
    ''' Source of drag '''

    def __init__(self, mass, drag_stowed, drag_deployed):
        Component.__init__(self, mass, drag_stowed)
        self._drag_stowed = float(drag_stowed)
        self._drag_deployed = float(drag_deployed)

    @property
    def drag_stowed(self):
        return self._drag_stowed

    @property
    def drag_deployed(self):
        return self._drag_deployed

    @property
    def drag(self):
        return self._drag

    def deploy(self):
        self._drag = self._drag_deployed

    def stow(self):
        self._drag = self._drag_stowed


@implementer(IEngine)
class Engine(Component):
    ''' A separate engine.  See also SRB '''

    def __init__(self, mass, drag, thrust, isp_atm, isp_vac):
        Component.__init__(self, mass, drag)
        self._thrust = float(thrust)
        self._isp_atm = float(isp_atm)
        self._isp_vac = float(isp_vac)

    @property
    def thrust(self):
        return self._thrust

    @property
    def isp_atm(self):
        return self._isp_atm

    @property
    def isp_vac(self):
        return self._isp_vac


@implementer(ITank)
class Tank(Component):
    ''' A fuel tank'''

    def __init__(self, mass, drag, mass_fuel):
        Component.__init__(self, mass, drag)
        self._mass_fuel = float(mass_fuel)

    @property
    def mass_fuel(self):
        return self._mass_fuel


class SRB(Engine, Tank):
    ''' A solid rocket booster'''

    def __init__(self, mass, drag, mass_fuel, thrust, isp_atm, isp_vac):
        Engine.__init__(self, mass, drag, thrust, isp_atm, isp_vac)
        Tank.__init__(self, mass, drag, mass_fuel)
        self._mass = mass
        self.mass_full = mass

    def isp(self, pressure):
        return (self.isp_atm - self.isp_vac) * pressure + self.isp_vac

    @property
    def thrust(self):
        if self.is_on():
            return self._thrust
        return 0.0

    @property
    def mass(self):
        return self._mass

    @mass.setter
    def mass(self, val):
        self._mass = val

    def is_on(self):
        return self.mass > (self.mass_full - self.mass_fuel)

    def tick(self, duration, pressure):
        mass = self.thrust / (self.isp(pressure) * 9.82) * duration
        self.mass -= mass

    def burn_time(self, pressure):
        return self.mass_fuel / self.thrust * self.isp(pressure) * 9.82

    def __str__(self):
        info = [
            'Engine info:\n',
            '  Fuel mass = ', str(self.mass_fuel), '\n',
            '  Isp (vac) = ', str(self.isp(0)), '\n',
            '  Isp (atm) = ', str(self.isp(1)), '\n',
            '  Thrust    = ', str(self.thrust), '\n',
            '  Burn time (vac)    = ', str(self.burn_time(0)), '\n',
            '  Burn time (atm)    = ', str(self.burn_time(1)),
        ]
        return ''.join(info)


# Command modules
CommandPodMk1 = Component(0.84, 0.2)
CommandPodMk1_2 = Component(4.0, 0.2)
StayputnikMk1 = Component(0.05, 0.2)

# Decouplers
TR_18A = Component(0.05, 0.2)
TT_38K = Component(0.025, 0.2)

# Parachutes
MK16 = Parachute(0.1, 0.22, 500)
MK16XL = Parachute(0.3, 0.22, 500)
MK2_R = Parachute(0.15, 0.22, 500)

# Science
Goo = Component(0.15, 0.1)
ScienceJr = Component(0.2, 0.2)
Communotron16 = Component(0.005, 0.2)
CommsDTS_M1 = Component(0.03, 0.2)

# Liquid Engines
LV_909 = Engine(0.5, 0.2, 50, 300, 390)
LV_T30 = Engine(1.25, 0.2, 215, 320, 370)
LV_T45 = Engine(1.5, 0.2, 200, 320, 370)

# Liquid Tanks
FL_T100 = Tank(0.5625, 0.2, 0.49)
FL_T200 = Tank(1.125, 0.2, 1.0)
FL_T400 = Tank(2.25, 0.2, 2.0)
FL_T800 = Tank(4.5, 0.2, 4.0)

# Solid rockets
RT_10 = SRB(3.7475, 0.3, 3.25, 250, 225, 240)
BACC = SRB(7.875, 0.3, 6.37, 315, 230, 250)


@implementer(IComponent)
class Stage(object):
    ''' A discrete rocket stage '''

    def __init__(self, components):
        if not all([IComponent.providedBy(x) for x in components]):
            raise TypeError('Stage elements must be IComponents')
        self.components = components
        self.engines = [x for x in self.components if IEngine.providedBy(x)]
        self.tanks = [x for x in self.components if ITank.providedBy(x)]
        self.chutes = [x for x in self.components if IParachute.providedBy(x)]

    @property
    def mass(self):
        return sum([x.mass for x in self.components])

    @property
    @memoized
    def mass_fuel(self):
        return sum([x.mass_fuel for x in self.tanks])

    @property
    def drag(self):
        return sum([x.mass * x.drag for x in self.components]) / self.mass

    def deploy_chutes(self):
        for chute in self.chutes:
            chute.deploy()

    def stow_chutes(self):
        for chute in self.chutes:
            chute.stow()

    @property
    def thrust(self):
        return sum([x.thrust for x in self.engines])

    @property
    @memoized
    def isp_atm(self):
        thrust = self.thrust
        denom = 0.0
        for engine in self.engines:
            denom += engine.thrust / engine.isp_atm
        return thrust / denom
        
    @property
    @memoized
    def isp_vac(self):
        thrust = self.thrust
        denom = 0.0
        for engine in self.engines:
            denom += engine.thrust / engine.isp_vac
        return thrust / denom

    @memoized
    def dv_atm(self, planet=Kerbin):
        ms = self.mass
        me = self.mass - self.mass_fuel
        return log(ms / me) * self.isp_atm * planet.gravity

    @memoized
    def dv_vac(self, planet=Kerbin):
        ms = self.mass
        me = self.mass - self.mass_fuel
        return log(ms / me) * self.isp_vac * planet.gravity
        
    @memoized
    def dv_true(self, planet=Kerbin):
        dva = self.dv_atm()
        dvv = self.dv_vac()
        dvo = planet.dv_out
        return (dva - dvo) / dva * dvv + dvo

    @memoized
    def twr(self, planet=Kerbin):
        mass = self.mass
        thrust = self.thrust
        return thrust / (mass * planet.gravity)

    def __str__(self):
        info = [
            'Stage info:\n',
            '  mass        : ', str(self.mass), '\n',
            '  fuel mass   : ', str(self.mass_fuel), '\n',
            '  thrust      : ', str(self.thrust), '\n',
            '  Isp (atm)   : ', str(self.isp_atm), '\n',
            '  Isp (vac)   : ', str(self.isp_vac), '\n',
            '  dv (vac)    : ', str(self.dv_vac()), '\n',
            '  dv (atm)    : ', str(self.dv_atm()), '\n',
            '  dv (Kerbin) : ', str(self.dv_true()), '\n',
            '  TWR         : ', str(self.twr()),
        ]
        return ''.join(info)


if __name__ == '__main__':
    from code import interact
    from pylab import *

    class Simulation(object):

        def __init__(self):
            self.rocket = Stage([CommandPodMk1, BACC])
            self.planet = Kerbin
            self.altitude = 0.0
            self.velocity = 0.0
            self.time = 0.0

        def running(self):
            return (any([x.is_on() for x in self.rocket.engines]) or
                    self.altitude > 0.0)

        def tick(self, duration):
            drag_factor = -1.0 if self.velocity < 0 else 1.0
            f = (self.rocket.thrust
                 - self.planet.g_force(self.altitude, self.rocket.mass)
                 - drag_factor * self.planet.d_force(self.altitude, self.velocity,
                                       self.rocket.mass, self.rocket.drag))
            a = f / self.rocket.mass
            self.altitude += self.velocity * duration
            self.velocity += a * duration
            self.time += duration

            for engine in self.rocket.engines:
                engine.tick(duration, self.planet.atmosphere.pressure(self.altitude))

        def run(self, tick=(1.0 / 30)):
            x = []
            y0 = []
            y1 = []
            y2 = []

            while self.running():
                self.tick(tick)
                x.append(self.time)
                y0.append(self.altitude)
                y1.append(self.velocity)
                y2.append(self.planet.terminal_velocity(self.altitude, self.rocket.drag))
            figure()
            plot(x, y0)
            figure()
            plot(x, y1, label='Rocket velocity')
            plot(x, y2, label='Optimal velocity')
            legend()
            show()

    sim = Simulation()
#    sim.run(0.01)

    interact('Welcome to the Kerbal Python Console', local=locals())
    
