
__author__    = "MIT ESP"
__date__      = "$DATE$"
__rev__       = "$REV$"
__license__   = "GPL v.2"
__copyright__ = """
This file is part of the ESP Web Site
Copyright (c) 2007 MIT ESP

The ESP Web Site is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

Contact Us:
ESP Web Group
MIT Educational Studies Program,
84 Massachusetts Ave W20-467, Cambridge, MA 02139
Phone: 617-253-4882
Email: web@esp.mit.edu
"""
from django.db import models
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User, AnonymousUser
from esp.datatree.models import DataTree, PermToString, GetNode, StringToPerm, get_lowest_parent
#from peak.api import security, binding
from esp.workflow.models import Controller
from datetime import datetime
from esp.db.models import Q, qlist
from esp.dblog.models import error
from django.db.models.query import QuerySet
from django.core.cache import cache
from datetime import datetime
from esp.middleware import ESPError
from django.template.defaultfilters import urlencode
from django.contrib.auth import logout, login, authenticate
from esp.db.fields import AjaxForeignKey

from esp.users.models.userbits import UserBit

try:
    import cPickle as pickle
except ImportError:
    import pickle
            




def user_get_key(user):
    """ Returns the key of the user, regardless of anything about the user object. """
    if user is None or type(user) == AnonymousUser or \
         (type(user) != User and type(user) != ESPUser) or \
         user.id is None:
        return 'None'
    else:
        return str(user.id)

def userBitCacheTime():
    return 300


class ESPUser(User, AnonymousUser):
    """ Create a user of the ESP Website
    This user extends the auth.User of django"""

    # this will allow a casting from User to ESPUser:
    #      foo = ESPUser(bar)   <-- foo is now an ``ESPUser''
    def __init__(self, userObj):
        if type(userObj) == ESPUser:
            self.__dict__ = userObj.__dict__
            self.__olduser = userObj.__olduser
        else:
            self.__dict__ = userObj.__dict__
            self.__olduser = userObj            

    @classmethod
    def ajax_autocomplete(cls, data):
        names = data.strip().split(',')
        last = names[0]

        query_set = cls.objects.filter(last_name__istartswith = last.strip())

        if len(names) > 1:
            first  = ','.join(names[1:])
            if len(first.strip()) > 0:
                query_set = query_set.filter(first_name__istartswith = first.strip())

        values = query_set.order_by('last_name','first_name','id').values('first_name', 'last_name', 'username', 'id')

        for value in values:
            value['ajax_str'] = '%s, %s (%s)' % (value['last_name'], value['first_name'], value['username'])
        return values

    def ajax_str(self):
        return "%s, %s (%s)" % (self.last_name, self.first_name, self.username)

    def getOld(self):
        if not self.__olduser:
            self.__olduser = User()
        self.__olduser.__dict__ = self.__dict__
        return self.__olduser

    def name(self):
        return '%s %s' % (self.first_name, self.last_name)

    def __cmp__(self, other):
        lastname = cmp(self.last_name.upper(), other.last_name.upper())
        if lastname == 0:
           return cmp(self.first_name.upper(), other.first_name.upper())
        return lastname

    def is_authenticated(self):
        return self.getOld().is_authenticated()

    def getVisible(self, objType):
        return UserBit.find_by_anchor_perms(objType, self, GetNode('V/Flags/Public'))

    def getLastProfile(self):
        from esp.program.models import RegistrationProfile
        return RegistrationProfile.getLastProfile(self)
        
    def getEditable(self, objType):
        return UserBit.find_by_anchor_perms(objType, self, GetNode('V/Administer/Edit'))

    def canEdit(self, object):
        return UserBit.UserHasPerms(self, object.anchor, GetNode('V/Administer/Edit'), datetime.now())

    def updateOnsite(self, request):
        if 'user_morph' in request.session:
            if request.session['user_morph']['onsite'] == True:
                self.onsite_local = True
                self.other_user   = True
                self.onsite_retTitle = request.session['user_morph']['retTitle']
                return True
            elif request.session['user_morph']['olduser'] is not None:
                self.other_user = True
                return False
        else:
            self.onsite_local = False
            self.other_user   = False
            return False


    def switch_to_user(self, request, user, retUrl, retTitle, onsite = False):
        user_morph = {'olduser' : self,
                      'retUrl'  : retUrl,
                      'retTitle': retTitle,
                      'onsite'  : onsite}

        request.session['user_morph'] = user_morph

        if type(user) == ESPUser:
            user = user.getOld()
            
        logout(request)
        
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        
        login(request, user)

    def get_old(self, request):
        if not 'user_morph' in request.session:
            return False
        return request.session['user_morph']['olduser']

    def switch_back(self, request):
        if not 'user_morph' in request.session:
            raise ESPError(), 'Error: You were not another user to begin with!'

        retUrl   = request.session['user_morph']['retUrl']
        new_user = request.session['user_morph']['olduser']
        
        del request.session['user_morph']
        
        logout(request)

        if type(new_user) == ESPUser:
            old_user = new_user.getOld()
            
        old_user.backend = 'django.contrib.auth.backends.ModelBackend'
        
        login(request, old_user)

        return retUrl
        

    def get_msg_vars(self, otheruser, key):
        """ This function will be called when rendering a message. """
        
        if key == 'name':
            return ESPUser(otheruser).name()
        elif key == 'recover_url':
            return 'http://esp.mit.edu/myesp/recoveremail/?code=%s' % \
                         otheruser.password
        elif key == 'username':
            return otheruser.username
        return ''
    
    def getTaughtClasses(self, program = None):
        """ Return all the taught classes for this user. If program is specified, return all the classes under
            that class. For most users this will return an empty queryset. """
        
        from esp.program.models import Class, Program # Need the Class object.
        all_classes = UserBit.find_by_anchor_perms(Class, self.getOld(), GetNode('V/Flags/Registration/Teacher'))
        
        if program is None: # If we have no program specified
            return all_classes
        else:
            if type(program) != Program: # if we did not receive a program
                error("Expects a real Program object. Not a `"+str(type(program))+"' object.")
            else:
                return all_classes.filter(parent_program = program)


    def getUserNum(self):
        """ Returns the "number" of a user, which is distinct from id.
            It's like the index if you search by lsat and first name."""
        
        users = User.objects.filter(last_name__iexact = self.last_name,
                                    first_name__iexact = self.first_name).order_by('id')
        i = 0
        for user in users:
            if user.id == self.id:
                break
            i += 1
            
        return (i and i or '')

    @staticmethod
    def getUserFromNum(first, last, num):
        if num == '':
            num = 0
        try:
            num = int(num)
        except:
            raise ESPError(), 'Could not find user "%s %s"' % (first, last)
            
        users = User.objects.filter(last_name__iexact = last,
                                    first_name__iexact = first).order_by('id')
        if len(users) <= num:
            raise ESPError(), 'Could not find user "%s %s"' % (first, last)
        
        return ESPUser(users[num])
        
    @staticmethod
    def getTypes():
        """ Get a list of the different roles an ESP user can have. By default there are four rols,
            but there can be more. (Returns ['Student','Teacher','Educator','Guardian']. """
        
        return ['Student','Teacher','Educator','Guardian']

    @staticmethod
    def getAllOfType(strType, QObject = True):
        now = datetime.now()
        Q_after_start = Q(userbit__startdate__isnull = True) | Q(userbit__startdate__lte = now)
        Q_before_end = Q(userbit__enddate__isnull = True) | Q(userbit__enddate__gte = now)

        types = ['Student', 'Teacher','Guardian','Educator']

        if strType not in types:
            raise ESPError(), "Invalid type to find all of."
                
        Q_useroftype      = Q(userbit__verb = GetNode('V/Flags/UserRole/'+strType)) &\
                            Q(userbit__qsc = GetNode('Q'))                          &\
                            Q_after_start                                  &\
                            Q_before_end

        if QObject:
            return Q_useroftype

        else:
            return User.objects.filter(Q_useroftype)


    def getEnrolledClasses(self):
        from esp.program.models import Class
        Conf = UserBit.find_by_anchor_perms(Class, self, GetNode('V/Flags/Registration/Confirmed'))
        Prel = UserBit.find_by_anchor_perms(Class, self, GetNode('V/Flags/Registration/Preliminary'))

        return (Conf | Prel).distinct()

    def isEnrolledInClass(self, clsObj):
        return UserBit.UserHasPerms(self, clsObj.anchor, GetNode('V/Flags/Registration/Confirmed')) or \
               UserBit.UserHasPerms(self, clsObj.anchor, GetNode('V/Flags/Registration/Preliminary'))
        
    def canAdminister(self, nodeObj):
        return UserBit.UserHasPerms(self, nodeObj.anchor, GetNode('V/Administer'))

    def isOnsite(self, program = None):
        verb = GetNode('V/Registration/OnSite')
        if program is None:
            return (hasattr(self, 'onsite_local') and self.onsite_local is True) or \
                   UserBit.objects.user_has_verb(self, verb)

        
        else:
            return UserBit.UserHasPerms(self, program.anchor, verb)

    def recoverPassword(self):
        # generate the code, send the email.
        
        import string
        import random
        from esp.users.models import PersistentQueryFilter
        from esp.db.models import Q
        from esp.dbmail.models import MessageRequest
        from django.template import loader, Context
        
        
        symbols = string.ascii_uppercase + string.digits 
        code = "".join([random.choice(symbols) for x in range(30)])
        
        # get the filter object
        filterobj = PersistentQueryFilter.getFilterFromQ(Q(id = self.id),
                                                         User,
                                                         'User %s' % self.username)
        
        curuser = User.objects.get(id = self.id)
        
        curuser.password = code
        curuser.save()
			
        # create the variable modules
        variable_modules = {'user': ESPUser(curuser)}


        newmsg_request = MessageRequest.createRequest(var_dict   = variable_modules,
                                                      subject    = '[ESP] Your Password Recovery For esp.mit.edu',
                                                      recipients = filterobj,
                                                      sender     = '"MIT Educational Studies Program" <esp@mit.edu>',
                                                      creator    = self,
                                                      msgtext    = loader.find_template_source('email/password_recover')[0])

        newmsg_request.save()



    def isAdministrator(self, program = None):
        if program is None:
            return UserBit.objects.user_has_verb(self, GetNode('V/Administer'))
        else:
            return UserBit.UserHasPerms(self, program.anchor, GetNode('V/Administer'))

    isAdmin = isAdministrator

    def delete(self):
        for x in self.userbit_set.all():
            x.delete()
        super(ESPUser, self).delete()
        
    
    def isTeacher(self):
        """Returns true if this user is a teacher"""
        return UserBit.UserHasPerms(self, GetNode('Q'), GetNode('V/Flags/UserRole/Teacher'))

    def isGuardian(self):
        """Returns true if this user is a teacher"""
        return UserBit.UserHasPerms(self, GetNode('Q'), GetNode('V/Flags/UserRole/Guardian'))

    def isEducator(self):
        """Returns true if this user is a teacher"""
        return UserBit.UserHasPerms(self, GetNode('Q'), GetNode('V/Flags/UserRole/Educator'))


    def isStudent(self):
        """Returns true if this user is a teacher"""
        return UserBit.UserHasPerms(self, GetNode('Q'), GetNode('V/Flags/UserRole/Student'))

    def canEdit(self, nodeObj):
        """Returns True or False if the user can edit the node object"""
        # Axiak
        return UserBit.UserHasPerms(self, nodeObj.anchor, GetNode('V/Administer/Edit'))

    def getMiniBlogEntries(self):
        """Return all miniblog posts this person has V/Subscribe bits for"""
        # Axiak 12/17
        from esp.miniblog.models import Entry
        return UserBit.find_by_anchor_perms(Entry, self, GetNode('V/Subscribe')).order_by('-timestamp')

    @staticmethod
    def isUserNameTaken(username):
        return len(User.objects.filter(username=username.lower()).values('id')[:1]) > 0

    @staticmethod
    def current_schoolyear():
        now = datetime.now()
        curyear = now.year
        if datetime(curyear, 7, 1) > now:
            schoolyear = curyear
        else:
            schoolyear = curyear + 1

        return schoolyear

    def getGrade(self, program = None):
        if not self.isStudent():
            return 0
        if program is None:
            regProf = self.getLastProfile()
        else:
            from esp.program.models import RegistrationProfile
            regProf = RegistrationProfile.getLastForProgram(self,program)
        if regProf and regProf.student_info:
            if regProf.student_info.graduation_year:
                return ESPUser.gradeFromYOG(regProf.student_info.graduation_year)

        return 0

    def currentSchoolYear(self):
        return ESPUser.current_schoolyear()-1

    @staticmethod
    def gradeFromYOG(yog):
        schoolyear = ESPUser.current_schoolyear()
        try:
            yog        = int(yog)
        except:
            return 0
        
        return schoolyear + 12 - yog
    
    @staticmethod
    def YOGFromGrade(grade):
        schoolyear = ESPUser.current_schoolyear()
        try:
            grade = int(grade)
        except:
            return 0

        return schoolyear + 12 - grade      
        

    
class StudentInfo(models.Model):
    """ ESP Student-specific contact information """
    user = AjaxForeignKey(User, blank=True, null=True)
    graduation_year = models.PositiveIntegerField(blank=True, null=True)
    school = models.CharField(maxlength=256,blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    studentrep = models.BooleanField(blank=True, null=True, default = False)


    
    def updateForm(self, form_dict):
        STUDREP_VERB = GetNode('V/Flags/UserRole/StudentRep')
        STUDREP_QSC  = GetNode('Q')
        
        form_dict['graduation_year'] = self.graduation_year
        form_dict['school']          = self.school
        form_dict['dob']             = self.dob
        form_dict['studentrep']      = UserBit.UserHasPerms(user = self.user,
                                                            qsc  = STUDREP_QSC,
                                                            verb = STUDREP_VERB)
        return form_dict        

    @staticmethod
    def addOrUpdate(curUser, regProfile, new_data):
        """ adds or updates a StudentInfo record """
        STUDREP_VERB = GetNode('V/Flags/UserRole/StudentRep')
        STUDREP_QSC  = GetNode('Q')
        
        if regProfile.student_info is None:
            studentInfo = StudentInfo()
            studentInfo.user = curUser
        else:
            studentInfo = regProfile.student_info
        
        studentInfo.graduation_year = new_data['graduation_year']
        studentInfo.school          = new_data['school']
        studentInfo.dob             = new_data['dob']
        studentInfo.save()
        if new_data['studentrep']:
            UserBit.objects.get_or_create(user = curUser,
                                          verb = STUDREP_VERB,
                                          qsc  = STUDREP_QSC,
                                          recursive = False)
        else:
            UserBit.objects.filter(user = curUser,
                                   verb = STUDREP_VERB,
                                   qsc  = STUDREP_QSC).delete()
            
        return studentInfo
    
    def __str__(self):
        username = "N/A"
        if self.user != None:
            username = self.user.username
        return 'ESP Student Info (%s)' % username
            
    class Admin:
        search_fields = ['user__first_name','user__last_name','user__username']


class TeacherInfo(models.Model):
    """ ESP Teacher-specific contact information """
    user = AjaxForeignKey(User, blank=True, null=True)
    graduation_year = models.PositiveIntegerField(blank=True, null=True)
    college = models.CharField(maxlength=128,blank=True, null=True)
    major = models.CharField(maxlength=32,blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    
    def updateForm(self, form_dict):
        form_dict['graduation_year'] = self.graduation_year
        form_dict['school']          = self.college
        form_dict['major']           = self.major
        form_dict['dob']             = self.dob
        return form_dict
    
    @staticmethod
    def addOrUpdate(curUser, regProfile, new_data):
        """ adds or updates a TeacherInfo record """
        if regProfile.teacher_info is None:
            teacherInfo = TeacherInfo()
            teacherInfo.user = curUser
        else:
            teacherInfo = regProfile.teacher_info
        
        teacherInfo.graduation_year = new_data['graduation_year']
        teacherInfo.college         = new_data['school']
        teacherInfo.major           = new_data['major']
        teacherInfo.dob           = new_data['dob']
        
        teacherInfo.save()
        return teacherInfo
                    
    def __str__(self):
        username = ""
        if self.user != None:
            username = self.user.username
        return 'ESP Teacher Info (%s)' % username

    class Admin:
        search_fields = ['user__first_name','user__last_name','user__username']
    
class GuardianInfo(models.Model):
    """ ES Guardian-specific contact information """
    user = AjaxForeignKey(User, blank=True, null=True)
    year_finished = models.PositiveIntegerField(blank=True, null=True)
    num_kids = models.PositiveIntegerField(blank=True, null=True)

    def updateForm(self, form_dict):
        form_dict['year_finished'] = self.year_finished
        form_dict['num_kids']      = self.num_kids
        return form_dict
    
    @staticmethod
    def addOrUpdate(curUser, regProfile, new_data):
        """ adds or updates a GuardianInfo record """
        if regProfile.guardian_info is None:
            guardianInfo = GuardianInfo()
            guardianInfo.user = curUser
        else:
            guardianInfo = regProfile.guardian_info
        
        guardianInfo.year_finished = new_data['year_finished']
        guardianInfo.num_kids      = new_data['num_kids']
        guardianInfo.save()
        return guardianInfo
    
    def __str__(self):
        username = ""
        if self.user != None:
            username = self.user.username
        return 'ESP Guardian Info (%s)' % username
    
    class Admin:
        search_fields = ['user__first_name','user__last_name','user__username']


class EducatorInfo(models.Model):
    """ ESP Educator-specific contact information """
    user = AjaxForeignKey(User, blank=True, null=True)
    subject_taught = models.CharField(maxlength=64,blank=True, null=True)
    grades_taught = models.CharField(maxlength=16,blank=True, null=True)
    school = models.CharField(maxlength=128,blank=True, null=True)
    position = models.CharField(maxlength=64,blank=True, null=True)
    
    def updateForm(self, form_dict):
        form_dict['subject_taught'] = self.subject_taught
        form_dict['grades_taught']  = self.grades_taught
        form_dict['school']         = self.school
        form_dict['position']       = self.position        
        return form_dict
    
    @staticmethod
    def addOrUpdate(curUser, regProfile, new_data):
        """ adds or updates a EducatorInfo record """
        if regProfile.educator_info is None:
            educatorInfo = EducatorInfo()
            educatorInfo.user = curUser
        else:
            educatorInfo = regProfile.educator_info
        
        educatorInfo.subject_taught = new_data['subject_taught']
        educatorInfo.grades_taught  = new_data['grades_taught']
        educatorInfo.position       = new_data['position']      
        educatorInfo.school         = new_data['school']
        educatorInfo.save()
        return educatorInfo
        
    def __str__(self):
        username = ""
        if self.user != None:
            username = self.user.username
        return 'ESP Educator Info (%s)' % username

    
    class Admin:
        search_fields = ['user__first_name','user__last_name','user__username']

class ZipCode(models.Model):
    """ Zip Code information """
    zip_code = models.CharField(maxlength=5)
    latitude = models.FloatField(max_digits=10, decimal_places = 6)
    longitude = models.FloatField(max_digits=10, decimal_places = 6)

    def distance(self, other):
        """ Returns the distance from one point to another """
        import math

        earth_radius = 3963.1676 # From google...
        
        lat1 = math.radians(self.latitude)
        lon1 = math.radians(self.longitude)
        lat2 = math.radians(other.latitude)
        lon2 = math.radians(other.longitude)

        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1

        tmp = math.sin(delta_lat/2.0)**2 + \
              math.cos(lat1)*math.cos(lat2) * \
              math.sin(delta_lon/2.0)**2

        distance = 2 * math.atan2(math.sqrt(tmp), math.sqrt(1-tmp)) * \
                   earth_radius

        return distance
    
    def close_zipcodes(self, distance):
        """ Get a list of zip codes less than or equal to
            distance from this zip code. """

        try:
            distance = float(distance)
        except:
            raise ESPError(), '%s should be a valid number!' % distance

        if distance < 0:
            distance *= -1

        oldsearches = ZipCodeSearches.objects.filter(zip_code = self,
                                                     distance = distance)

        if len(oldsearches) > 0:
            return oldsearches[0].zipcodes.split(',')
                                             
        
        all_zips = list(ZipCode.objects.exclude(id = self.id))
        winners  = [ self.zip_code ]

        winners += [ zipc.zip_code for zipc in all_zips
                     if self.distance(zipc) <= distance ]

        newsearch = ZipCodeSearches(zip_code = self,
                                    distance = distance,
                                    zipcodes = ','.join(winners))
        newsearch.save()
        
        return winners

    def __str__(self):
        return '%s (%s, %s)' % (self.zip_code,
                                self.longitude,
                                self.latitude)



class ZipCodeSearches(models.Model):
    zip_code = models.ForeignKey(ZipCode)
    distance = models.FloatField(max_digits = 15, decimal_places = 3)
    zipcodes = models.TextField()

    def __str__(self):
        return '%s Zip Codes that are less than %s miles from %s' % \
               (len(self.zipcodes.split(',')), self.distance, self.zip_code)

class ContactInfo(models.Model):
	""" ESP-specific contact information for (possibly) a specific user """
	user = AjaxForeignKey(User, blank=True, null=True, edit_inline = models.STACKED)
	first_name = models.CharField(maxlength=64)
	last_name = models.CharField(maxlength=64)        
	e_mail = models.EmailField(blank=True, null=True)
	phone_day = models.PhoneNumberField(blank=True, null=True)
	phone_cell = models.PhoneNumberField(blank=True, null=True, core=True)
	phone_even = models.PhoneNumberField(blank=True, null=True)
	address_street = models.CharField(maxlength=100,blank=True, null=True, core=True)
	address_city = models.CharField(maxlength=50,blank=True, null=True, core=True)
	address_state = models.USStateField(blank=True, null=True, core=True)
	address_zip = models.CharField(maxlength=5,blank=True, null=True, core=True)
        address_postal = models.TextField(blank=True,null=True)
        undeliverable = models.BooleanField(default=False, core=True)
        
        def address(self):
            return '%s, %s, %s %s' % \
                   (self.address_street,
                    self.address_city,
                    self.address_state,
                    self.address_zip)
                    

        def items(self):
            return self.__dict__.items()

        @staticmethod
        def addOrUpdate(regProfile, new_data, contactInfo, prefix='', curUser=None):
            """ adds or updates a ContactInfo record """
            if contactInfo is None:
                contactInfo = ContactInfo()
            for i in contactInfo.__dict__.keys():
                if i != 'user_id' and i != 'id' and new_data.has_key(prefix+i):
                    contactInfo.__dict__[i] = new_data[prefix+i]
            if curUser is not None:
                contactInfo.user = curUser
            contactInfo.save()
            return contactInfo

        def updateForm(self, form_data, prepend=''):
            newkey = self.__dict__
            for key, val in newkey.items():
                if val and key != 'id':
                    form_data[prepend+key] = str(val)
            return form_data

        def save(self):

            

            if self.id != None:
                try:
                    old_self = ContactInfo.objects.get(id = self.id)
                    if old_self.address_zip != self.address_zip or \
                       old_self.address_street != self.address_street or \
                       old_self.address_city != self.address_city or \
                       old_self.address_state != self.address_state:
                        self.address_postal = None
                        self.undeliverable = False
                except:
                    pass
            
            if self.address_postal != None:
                self.address_postal = str(self.address_postal)

            
            models.Model.save(self)
                
	def __str__(self):
            username = ""
            last_name, first_name = '', ''
            if self.user != None:
                username = self.user.username
            if self.first_name is not None:
                first_name = self.first_name
            if self.last_name is not None:
                last_name = self.last_name
            return first_name + ' ' + last_name + ' (' + username + ')'

	class Admin:
            search_fields = ['first_name','last_name','user__username']


class K12School(models.Model):
    """
    All the schools that we know about.
    """
    contact = models.ForeignKey(ContactInfo, null=True,blank=True)
    school_type = models.TextField(blank=True,null=True)
    grades      = models.TextField(blank=True,null=True)
    school_id   = models.CharField(maxlength=128,blank=True,null=True)
    contact_title = models.TextField(blank=True,null=True)
    name          = models.TextField(blank=True,null=True)

    def __str__(self):
        if self.contact_id:
            return '"%s" in %s, %s' % (self.name, self.contact.address_city,
                                       self.contact.address_state)
        else:
            return '"%s"' % self.name
    
    class Admin:
        pass

def GetNodeOrNoBits(nodename, user = AnonymousUser(), verb = None, create=True):
    """ Get the specified node.  Create it only if the specified user has create bits on it """

    DEFAULT_VERB = 'V/Administer/Edit'

    # get a node, if it exists, return it.
    try:
        node = DataTree.get_by_uri(nodename)
        return node
    except:
        pass


    # if we weren't given a verb, use the default one
    if verb == None:
        verb = GetNode(DEFAULT_VERB)

    # get the lowest parent that exists
    lowest_parent = get_lowest_parent(nodename)

    if UserBit.UserHasPerms(user, lowest_parent, verb, recursive_required = True):
        if create:
            # we can now create it
            return GetNode(nodename)
        else:
            raise DataTree.NoSuchNodeException(lowest_parent, nodename)
    else:
        # person not allowed to
        raise PermissionDenied


class PersistentQueryFilter(models.Model):
    """ This class stores generic query filters persistently in the database, for retrieval (by ID, presumably) and
        to pass the query along to multiple pages and retrival (et al). """
    
    item_model   = models.CharField(maxlength=256)            # A string representing the model, for instance User or Program
    q_filter     = models.TextField()                         # A string representing a query filter
    sha1_hash    = models.CharField(maxlength=256)            # A sha1 hash of the string representing the query filter
    create_ts    = models.DateTimeField(auto_now_add = True)  # The create timestamp
    useful_name  = models.CharField(maxlength=1024, blank=True, null=True) # A nice name to apply to this filter.



    @staticmethod
    def create_from_Q(item_model, q_filter, description = ''):
        """ The main constructor, please call this. """
        import sha

        dumped_filter = pickle.dumps(q_filter)
        
        foo, created = PersistentQueryFilter.objects.get_or_create(item_model = str(item_model),
                                                                   q_filter = dumped_filter,
                                                                   sha1_hash = sha.new(dumped_filter).hexdigest())
        
        
        foo.useful_name = description

        foo.save()
        
        return foo
        
        

    def get_Q(self):
        """ This will return the Q object that was passed into it. """
        try:
            QObj = pickle.loads(self.q_filter)
        except:
            raise ESPError(), 'Invalid Q object stored in database.'


        return QObj

    def getList(self, module):
        """ This will actually return the list generated from the filter applied
            to the live database. You must supply the model. If the model is not matched,
            it will become an error. """

        if str(module) != str(self.item_model):
            raise ESPError(), 'The module given does not match that of the persistent entry.'

        return module.objects.filter(self.get_Q())

    @staticmethod
    def getFilterFromID(id, model):
        """ This function will return a PQF object from the id given. """
        try:
            id = int(id)
        except:
            assert False, 'The query filter id given is invalid.'

 
        return PersistentQueryFilter.objects.get(id = id,
                                                 item_model = str(model))
    
 
                


    @staticmethod
    def getFilterFromQ(QObject, model, description = ''):
        """ This function will get the filter from the Q object. It will either create one
            or use an old one depending on whether it's been used. """

        import sha
        
        try:
            qobject_string = pickle.dumps(QObject)
        except:
            qobject_string = ''


        
        try:
            filterObj = PersistentQueryFilter.objects.get(sha1_hash = sha.new(qobject_string).hexdigest())#    pass
        except:
            filterObj = PersistentQueryFilter.create_from_Q(item_model  = model,
                                                            q_filter    = QObject,
                                                            description = description)
            filterObj.save() # create a new one.

        return filterObj

    def __str__(self):
        return str(self.useful_name)
        

class ESPUser_Profile(models.Model):
    user = models.ForeignKey(User, unique=True)

    def prof(self):
        return ESPUser(self.user)


class DBList(object):
    """ Useful abstraction for the list of users.
        Not meant for anything but users_get_list...
    """
    totalnum = False # we dont' know how many there are.
    key      = ''
    QObject  = None
    
    
    def count(self, override = False):
        """ This is used to count how many objects wer are talking about.
            If override is true, it will not retrieve the number from cache
            or from this instance. If it's true, it will try.
        """
        
        from esp.users.models import User

        cache_id = urlencode('DBListCount: %s' % (self.key))

        retVal   = cache.get(cache_id) # get the cached result
 
        if self.QObject: # if there is a q object we can just 
            if not self.totalnum:
                if override:
                    self.totalnum = User.objects.filter(self.QObject).distinct().count()
                    cache.set(cache_id, self.totalnum, 60)
                else:
                    cachedval = cache.get(cache_id)
                    if cachedval is None:
                        self.totalnum = User.objects.filter(self.QObject).distinct().count()
                        cache.set(cache_id, self.totalnum, 60)
                    else:
                        self.totalnum = cachedval

            return self.totalnum
        else:
            return 0
        
    def id(self):
        """ The id is the same as the key, it is client-specified. """
        return self.key
    
    def __init__(self, **kwargs):
        self.__dict__ = kwargs

    def __cmp__(self, other):
        """ We are going to order by the size of our lists. """
        return cmp(self.count(), other.count())
    
    def __str__(self):
        return self.key




