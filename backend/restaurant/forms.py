from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import (
    EtaRule,
    RestaurantSettings,
    RestaurantTable,
    WaitlistEntry,
    WorkerProfile,
)
from .services import calculate_estimated_wait_minutes


LOCATION_PREFERENCE_CHOICES = (
    ('no_preference', 'No preference'),
    ('indoor', 'Indoor'),
    ('outdoor', 'Outdoor'),
)
SEATING_PREFERENCE_CHOICES = (
    ('no_preference', 'No preference'),
    ('standard', 'Standard table'),
    ('booth', 'Booth'),
    ('bar', 'Bar seating'),
)
HIGH_CHAIR_CHOICES = (
    ('no', 'No'),
    ('yes', 'Yes'),
)
MAX_GRACE_PERIOD_MINUTES = 240


ROLE_CHOICES = (
    (WorkerProfile.Role.STAFF, WorkerProfile.Role.STAFF.label),
    (WorkerProfile.Role.MANAGER, WorkerProfile.Role.MANAGER.label),
)


class WorkerAccountCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label='Password confirmation',
        strip=False,
        widget=forms.PasswordInput,
    )
    is_active = forms.BooleanField(required=False, initial=True)
    role = forms.ChoiceField(choices=ROLE_CHOICES)

    def clean_username(self):
        username = self.cleaned_data['username']
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('A user with that username already exists.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The two password fields did not match.')

        if password1:
            try:
                validate_password(password1)
            except forms.ValidationError as error:
                self.add_error('password1', error)

        return cleaned_data

    def save(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data.get('first_name', ''),
            last_name=self.cleaned_data.get('last_name', ''),
            email=self.cleaned_data.get('email', ''),
            is_active=self.cleaned_data.get('is_active', False),
        )
        WorkerProfile.objects.create(
            user=user,
            role=self.cleaned_data['role'],
        )
        return user


class WorkerAccountEditForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    is_active = forms.BooleanField(required=False)
    role = forms.ChoiceField(choices=ROLE_CHOICES)

    def __init__(self, *args, user, current_user, **kwargs):
        self.user = user
        self.current_user = current_user
        initial = {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_active': user.is_active,
            'role': user.worker_profile.role,
        }
        kwargs.setdefault('initial', initial)
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data['username']
        user_model = get_user_model()
        duplicate = (
            user_model.objects.filter(username=username)
            .exclude(pk=self.user.pk)
            .exists()
        )
        if duplicate:
            raise forms.ValidationError('A user with that username already exists.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        if self.user.pk == self.current_user.pk:
            if cleaned_data.get('role') != WorkerProfile.Role.MANAGER:
                self.add_error('role', 'You cannot remove your own Manager access.')
            if not cleaned_data.get('is_active'):
                self.add_error('is_active', 'You cannot deactivate your own account.')
        return cleaned_data

    def save(self):
        self.user.username = self.cleaned_data['username']
        self.user.first_name = self.cleaned_data.get('first_name', '')
        self.user.last_name = self.cleaned_data.get('last_name', '')
        self.user.email = self.cleaned_data.get('email', '')
        self.user.is_active = self.cleaned_data.get('is_active', False)
        self.user.save()

        profile = self.user.worker_profile
        profile.role = self.cleaned_data['role']
        profile.save()
        return self.user


class RestaurantTableForm(forms.ModelForm):
    class Meta:
        model = RestaurantTable
        fields = ['identifier', 'capacity', 'status']

    def clean_capacity(self):
        capacity = self.cleaned_data['capacity']
        if capacity <= 0:
            raise forms.ValidationError('Capacity must be greater than zero.')
        return capacity


class EtaRuleForm(forms.ModelForm):
    class Meta:
        model = EtaRule
        fields = [
            'min_party_size',
            'max_party_size',
            'estimated_wait_minutes',
            'is_active',
        ]

    def clean_min_party_size(self):
        min_party_size = self.cleaned_data['min_party_size']
        if min_party_size <= 0:
            raise forms.ValidationError(
                'Minimum party size must be greater than zero.'
            )
        return min_party_size

    def clean_max_party_size(self):
        max_party_size = self.cleaned_data.get('max_party_size')
        if max_party_size is not None and max_party_size <= 0:
            raise forms.ValidationError(
                'Maximum party size must be greater than zero.'
            )
        return max_party_size

    def clean_estimated_wait_minutes(self):
        estimated_wait_minutes = self.cleaned_data['estimated_wait_minutes']
        if estimated_wait_minutes <= 0:
            raise forms.ValidationError(
                'Estimated wait minutes must be greater than zero.'
            )
        return estimated_wait_minutes

    def clean(self):
        cleaned_data = super().clean()
        min_party_size = cleaned_data.get('min_party_size')
        max_party_size = cleaned_data.get('max_party_size')
        is_active = cleaned_data.get('is_active')

        if (
            min_party_size is not None
            and max_party_size is not None
            and max_party_size < min_party_size
        ):
            self.add_error(
                'max_party_size',
                (
                    'Maximum party size must be greater than or equal to '
                    'minimum party size.'
                ),
            )

        if min_party_size is not None and is_active:
            overlapping_rules = EtaRule.objects.filter(is_active=True)
            if self.instance.pk:
                overlapping_rules = overlapping_rules.exclude(pk=self.instance.pk)

            for rule in overlapping_rules:
                if _eta_ranges_overlap(
                    min_party_size,
                    max_party_size,
                    rule.min_party_size,
                    rule.max_party_size,
                ):
                    self.add_error(
                        None,
                        'Active party-size ETA rules cannot overlap.',
                    )
                    break

        return cleaned_data


def _eta_ranges_overlap(first_min, first_max, second_min, second_max):
    first_upper = first_max if first_max is not None else float('inf')
    second_upper = second_max if second_max is not None else float('inf')
    return first_min <= second_upper and second_min <= first_upper


class GracePeriodForm(forms.ModelForm):
    grace_period_minutes = forms.IntegerField()

    class Meta:
        model = RestaurantSettings
        fields = ['grace_period_minutes']

    def clean_grace_period_minutes(self):
        grace_period_minutes = self.cleaned_data['grace_period_minutes']
        if grace_period_minutes <= 0:
            raise forms.ValidationError(
                'Grace period must be greater than zero minutes.'
            )
        if grace_period_minutes > MAX_GRACE_PERIOD_MINUTES:
            raise forms.ValidationError(
                f'Grace period cannot exceed {MAX_GRACE_PERIOD_MINUTES} minutes.'
            )
        return grace_period_minutes


class GuestCheckInForm(forms.Form):
    guest_name = forms.CharField(label='Guest name', max_length=255)
    party_size = forms.IntegerField(
        label='Party size',
        min_value=1,
        widget=forms.NumberInput(attrs={'min': 1}),
    )
    phone_number = forms.CharField(
        label='Phone number',
        max_length=255,
        required=False,
    )
    location_preference = forms.ChoiceField(
        label='Indoor/outdoor preference',
        choices=LOCATION_PREFERENCE_CHOICES,
        required=False,
    )
    seating_preference = forms.ChoiceField(
        label='Seating preference',
        choices=SEATING_PREFERENCE_CHOICES,
        required=False,
    )
    accessibility_requirements = forms.CharField(
        label='Accessibility requirements',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    high_chair_needed = forms.ChoiceField(
        label='High chair need',
        choices=HIGH_CHAIR_CHOICES,
        required=False,
        widget=forms.RadioSelect,
    )
    notes = forms.CharField(
        label='Notes',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def save(self):
        preference_parts = []
        for field_name in [
            'location_preference',
            'seating_preference',
            'accessibility_requirements',
            'high_chair_needed',
            'notes',
        ]:
            value = self.cleaned_data.get(field_name)
            if value:
                label = self.fields[field_name].label
                preference_parts.append(f'{label}: {value}')

        party_size = self.cleaned_data['party_size']
        estimated_wait_minutes = calculate_estimated_wait_minutes(party_size)

        return WaitlistEntry.objects.create(
            guest_name=self.cleaned_data['guest_name'],
            party_size=party_size,
            contact_text=self.cleaned_data.get('phone_number', ''),
            preference_notes='\n'.join(preference_parts),
            estimated_wait_minutes=estimated_wait_minutes,
        )
