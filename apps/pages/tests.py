from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()

class AdminDashboardCacheTest(TestCase):
    def setUp(self):
        # Create a superuser to access the admin dashboard
        self.user = User.objects.create_superuser(
            email='admin@example.com',
            password='password123',
            full_name='Admin User'
        )
        self.client = Client()
        self.client.login(email='admin@example.com', password='password123')

    def test_flush_all_cache_action(self):
        # Set some cache values
        cache.set('test_key_1', 'value_1')
        cache.set('test_key_2', 'value_2')
        self.assertEqual(cache.get('test_key_1'), 'value_1')
        self.assertEqual(cache.get('test_key_2'), 'value_2')

        # Send POST request to admin_dashboard with flush_all_cache action
        response = self.client.post(reverse('admin_dashboard'), {'flush_all_cache': '1'})
        
        # Verify redirect to admin_dashboard
        self.assertRedirects(response, reverse('admin_dashboard'))

        # Check if cache is cleared
        self.assertIsNone(cache.get('test_key_1'))
        self.assertIsNone(cache.get('test_key_2'))
