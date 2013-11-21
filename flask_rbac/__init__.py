#-*- coding: utf-8 -*-
"""
    flaskext.rbac
    ~~~~~~~~~~~~~

    Adds Role-based Access Control module to application.

"""
import itertools

from flask import request, abort


class RBACRoleMixinModel(object):
    '''
    This mixin class provides implementations for the methods of Role model
    needed by Flask-RBAC.
    '''
    def get_name(self):
        '''Return the name of this role'''
        return self.name

    def get_parents(self):
        '''Iterate parents of this role'''
        for parent in self.parents:
            yield parent

    def get_family(self):
        '''Return family of this role'''
        for parent in self.parents:
            if parent.parents:
                parent.get_parents()
            yield parent
        yield self

    @staticmethod
    def get_by_name(name):
        return everyone


class RBACUserMixinModel(object):
    '''
    This mixin class provides implementations for the methods of User model
    needed by Flask-RBAC.
    '''
    def get_roles(self):
        '''Return roles of this user'''
        for role in self.roles:
            role.get_family()


class EveryoneRole(RBACRoleMixinModel):

    def __init__(self):
        self.name = 'Everyone'
        self.parents = []


everyone = EveryoneRole()


class PermissionDeny(Exception):
    def __init__(self, message="", **kwargs):
        super(PermissionDenied, self).__init__(message)
        self.kwargs = kwargs
        self.kwargs['message'] = message


class AccessControlList(object):
    '''
    This class record data for access controling.
    '''
    def __init__(self):
        self._allowed = []
        self._denied = []

    def allow(self, role, method, resource):
        '''Add a allowing rule.'''
        # assert role in self._roles
        # assert resource in self._resources
        permission = (role, method, resource)
        if not permission in self._allowed:
            self._allowed.append(permission)

    def deny(self, role, method, resource):
        '''Add a denying rule.'''
        # assert role in self._roles
        # assert resource in self._resources
        permission = (role, method, resource)
        if not permission in self._denied:
            self._denied.append(permission)

    def is_allowed(self, role, method, resource):
        return (role, method, resource) in self._allowed

    def is_denied(self, role, method, resource):
        return (role, metho, resourced) in self._denied


class _RBACState(object):
    '''Records configuration for Flask-RBAC'''
    def __init__(self, rbac, app):
        self.rbac = rbac
        self.app = app


class RBAC(object):
    '''This class implements role-base access control module in flask.

    There are two way to initialize Flask-RBAC:

        app = Flask(__name__)
        rbac = RBAC(app)

    or

        rbac = RBAC
        def create_app():
            app = Flask(__name__)
            rbac.init_app(app)
            return app

    Difference between two ways see:
    https://github.com/mitsuhiko/flask-sqlalchemy/blob/master/flask_sqlalchemy/__init__.py#L592
    '''
    def __init__(self, app=None, **kwargs):
        self.acl = AccessControlList()
        self._role_model = kwargs.get('role_model', RBACRoleMixinModel)
        self._user_model = kwargs.get('user_model', RBACUserMixinModel)
        self._user_loader = kwargs.get('user_loader', None)

        if app is not None:
            self.init_app(app)
        else:
            self.app = None

    def init_app(self, app):
        '''
        Initialize application in Flask-RBAC.

        Adds (RBAC, app) to flask extensions.
        Adds hook to authenticate permission before request.
        '''
        self.app = app

        if not hasattr(app, 'extensions'):
            app.extensions = {}
        app.extensions['rbac'] = _RBACState(self, app)

        app.before_request(self._authenticate)

    def set_role_model(self, model):
        '''Set custom model of Role.'''
        needed_methods = ['get_name', 'get_parents', 'get_by_name']
        for method in needed_methods:
            if not method in dir(model):
                raise NotImplementedError("%s didn't implement %s method!" %
                                          model.__class__, method)
        self._role_model = model

    def set_user_model(self, model):
        '''Set custom model of User.'''
        needed_methods = ['get_roles']
        for method in needed_methods:
            if not method in dir(model):
                raise NotImplementedError("%s didn't implement %s method!" %
                                          model.__class__, method)
        self._user_model = model

    def set_user_loader(self, loader):
        '''Set user loader, which is used to load current user'''
        self._user_loader = loader

    def _authenticate(self):
        '''Authenticate permission'''
        assert self.app, "Please initialize your application into Flask-RBAC."
        assert self._role_model, "Please set role model before authenticate."
        assert self._user_model, "Please set user model before authenticate."
        assert self._user_loader, "Please set user loader before authenticate."

        current_user = self._user_loader()
        assert (type(current_user) == self._user_model,
                "%s is not an instance of %s" %
                (current_user, self._user_model.__class__))

        endpoint = request.endpoint
        resource = self.app.view_functions.get(endpoint, None)
        if not resource:
            abort(404)

        method = request.method

        if not hasattr(current_user, 'roles'):
            roles = [everyone]
        else:
            roles = current_user.roles

        for role in roles:
            if self.check_permission(role, method, resource) == False:
                abort(405)

    def check_permission(self, role, method, resource):
        roles = set(role.get_family())
        methods = set([None, method])
        resources = set([None, resource])
        is_allowed = None

        for r, m, res in itertools.product(roles, methods, resources):
            permission = (r.get_name(), m, res)
            if permission in self.acl._denied:
                return False

            if permission in self.acl._allowed:
                is_allowed = True

        print is_allowed
        return is_allowed

    def has_permission(self, role, method, resource):
        return bool(check_permission(role, method, resource) == True)

    def check_perm(self, role, method):
        def decorator(fview_func):
            if not self.check_permission(role, method, view_func):
                abort(405)
            return view_func
        return decorator

    def resource_decorator(self):
        def decorator(view_func):
            self.acl.add_resource(view_func)
            return view_func
        return decorator

    def allow_decorator(self, role, method):
        def decorator(view_func):
            method.upper()
            self.acl.allow(role, method, view_func)
            return view_func
        return decorator

    def deny_decorator(self, role, method):
        def decorator(view_func):
            method.upper()
            self.acl.deny(role, method, view_func)
            return view_func
        return decorator
