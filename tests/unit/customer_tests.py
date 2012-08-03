import httplib

from django.test.client import Client
from django.test import TestCase
from django.http import HttpRequest
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django_dynamic_fixture import get

from oscar.test import ClientTestCase
from oscar.apps.customer.models import CommunicationEventType
from oscar.apps.customer.history_helpers import get_recently_viewed_product_ids
from oscar.test.helpers import create_product, create_order

from oscar.apps.catalogue.notification.models import ProductNotification


class HistoryHelpersTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.product = create_product()

    def test_viewing_product_creates_cookie(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertTrue('oscar_recently_viewed_products' in response.cookies)

    def test_id_gets_added_to_cookie(self):
        response = self.client.get(self.product.get_absolute_url())
        request = HttpRequest()
        request.COOKIES['oscar_recently_viewed_products'] = response.cookies['oscar_recently_viewed_products'].value
        self.assertTrue(self.product.id in get_recently_viewed_product_ids(request))


class CommunicationTypeTest(TestCase):
    keys = ('body', 'html', 'sms', 'subject')

    def test_no_templates_returns_empty_string(self):
        et = CommunicationEventType()
        messages = et.get_messages()
        for key in self.keys:
            self.assertEqual('', messages[key])

    def test_field_template_render(self):
        et = CommunicationEventType(email_subject_template='Hello {{ name }}')
        ctx = {'name': 'world'}
        messages = et.get_messages(ctx)
        self.assertEqual('Hello world', messages['subject'])


class AnonOrderDetail(TestCase):

    def setUp(self):
        self.client = Client()

    def test_404_received_for_unknown_order(self):
        response = self.client.get(reverse('customer:anon-order', kwargs={'order_number': 1000,
            'hash': '1231231232'}))
        self.assertEqual(httplib.NOT_FOUND, response.status_code)

    def test_200_received_for_order_with_correct_hash(self):
        order = create_order()
        response = self.client.get(reverse('customer:anon-order', kwargs={'order_number': order.number,
            'hash': order.verification_hash()}))
        self.assertEqual(httplib.OK, response.status_code)

    def test_404_received_for_order_with_incorrect_hash(self):
        order = create_order()
        response = self.client.get(reverse('customer:anon-order', kwargs={'order_number': order.number,
            'hash': 'bad'}))
        self.assertEqual(httplib.NOT_FOUND, response.status_code)


class EditProfileTests(TestCase):
    username = 'customer'
    password = 'cheeseshop'
    email = 'customer@example.com'

    def setUp(self):
        User.objects.create_user(username=self.username,
                                 email=self.email, password=self.password)
        is_successful = self.client.login(username=self.username,
                                          password=self.password)
        if not is_successful:
            self.fail("Unable to login as %s" % self.username)

    def tearDown(self):
        User.objects.all().delete()

    def test_update_profile_page_for_smoke(self):
        url = reverse('customer:profile-update')
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertTrue('form' in response.context)


class AccountRegistrationViewTest(ClientTestCase):
    is_anonymous = True
    username = 'newuser'
    password = 'zlkdsjflk3jSvj'
    email = 'newuser@oscar.com'

    def setUp(self):
        super(AccountRegistrationViewTest, self).setUp()

    def test_assigning_anonymous_notifications_to_new_registered_user(self):
        """
        Test that anonymous notifications are assigned correctly to a
        user that registers an account. This is based on email addresses
        and as long as the account email address matches the notification
        email field it will be changed accordingly.
        """
        get(ProductNotification, user=None, email=self.email)
        get(ProductNotification, user=None, email=self.email)
        get(ProductNotification, user=None, email='some@other.com')

        for notification in ProductNotification.objects.all():
            self.assertEquals(notification.user, None)
        self.assertEquals(ProductNotification.objects.count(), 3)

        response = self.client.post(reverse('customer:register'), data={
            'registration-email': self.email,
            'registration-password1': self.password,
            'registration-password2': self.password,
        }, follow=True)

        self.assertContains(response, "Account", status_code=200)

        user = User.objects.get(email=self.email)
        user_notifications = ProductNotification.objects.filter(user=user)
        self.assertEquals(len(user_notifications), 2)


class AuthTestCase(TestCase):

    username = 'customer'
    password = 'cheeseshop'
    email = 'customer@example.com'

    def setUp(self):
        self.client = Client()
        self.product = create_product()
        User.objects.create_user(username=self.username,
                                 email=self.email, password=self.password)
        self.client.login(username=self.username, password=self.password)

    def test_cookies_deleted_on_logout(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertTrue('oscar_recently_viewed_products' in response.cookies)

        response = self.client.get(reverse('customer:logout'))
        self.assertTrue(('oscar_recently_viewed_products' not in response.cookies)
                        or not
                        self.client.cookies['oscar_recently_viewed_products'].coded_value)


class AuthStaffRedirectTests(TestCase):
    username = 'staff'
    password = 'cheeseshop'
    email = 'staff@example.com'

    def test_staff_member_login_for_dashboard(self):
        """
        Test if a staff member that is not yet logged in and trying to access the
        dashboard is redirected to the Oscar login page (instead of the ``admin``
        login page). Also test that the redirect after successful login will
        be the originally requested page.
        """
        self.client = Client()
        user = User.objects.create_user(username=self.username,
                                    email=self.email, password=self.password)
        user.is_staff = True
        user.save()

        response = self.client.get(reverse('dashboard:index'), follow=True)
        self.assertContains(response, "login-username", status_code=200)
        self.assertEquals(response.context['next'], reverse('dashboard:index'))
