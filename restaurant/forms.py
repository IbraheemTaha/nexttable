from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import RestaurantTable, WorkerProfile


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
