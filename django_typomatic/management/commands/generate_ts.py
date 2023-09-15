import inspect
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
import sys

from django_typomatic import ts_interface, generate_ts
from rest_framework.serializers import BaseSerializer


def _get_serializers_for_module(module_name, serializer_name=None):
    serializers = []
    module = sys.modules.get(module_name, None)
    possibly_serializers = filter(lambda name: not name.startswith('_'), dir(module))

    for serializer_class_name in possibly_serializers:
        serializer_class = getattr(module, serializer_class_name)

        if not inspect.isclass(serializer_class):
            continue

        # Skip imported serializer classes
        if module_name not in serializer_class.__module__:
            continue

        if serializer_name and serializer_class.__name__ != serializer_name:
            continue

        if issubclass(serializer_class, BaseSerializer):
            serializers.append(serializer_class)

    return serializers


class Command(BaseCommand):
    help = 'Generate TS types from serializer'

    @property
    def log_output(self):
        return self.stdout

    def log(self, msg):
        self.log_output.write(msg)

    def add_arguments(self, parser):
        parser.add_argument(
            '--serializers',
            '-s',
            help='Serializers enumeration '
                 'formats: module_name.SerializerName | module_name.serializers.submodule | module_name',
            nargs="*",
            type=str,
            default=[]
        )
        parser.add_argument(
            '--all',
            help='Generate TS types for all project serializers',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '--trim',
            '-t',
            help='Trim "serializer" from type name',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '--camelize',
            '-c',
            help='Camelize field names',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '--annotations',
            '-a',
            help='Add js doc annotations for validations (eg. for Zod)',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '--enum_choices',
            '-ec',
            help='Add choices to external enum type instead union',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '--enum_values',
            '-ev',
            help='Add enum for obtain display name for choices field',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '--enum_keys',
            '-ek',
            help='Add enum keys by values for obtain display name for choices field',
            default=False,
            action='store_true'
        )
        parser.add_argument(
            '-o',
            '--output',
            help='Output folder for save TS files, by default save as ./types folder',
            default='./types'
        )

    @staticmethod
    def _get_app_serializers(app_name):
        return _get_serializers_for_module(f'{app_name}.serializers')

    @staticmethod
    def _get_submodule_serializers(submodule):
        return _get_serializers_for_module(submodule)

    def _generate_ts(self, serializer_class, output, **options):
        app_name = serializer_class.__module__.split(".")[0]

        ts_interface(context=app_name)(serializer_class)

        output_path = Path(output) / app_name / 'index.ts'

        generate_ts(
            output_path,
            context=app_name,
            enum_choices=options['enum_choices'],
            enum_values=options['enum_values'],
            enum_keys=options['enum_keys'],
            camelize=options['camelize'],
            trim_serializer_output=options['trim'],
            annotations=options['annotations']
        )
        self.stdout.write(f'[+] {serializer_class.__module__}.{serializer_class.__name__}')

    def handle(self, *args, serializers, output, all, **options):
        if all and serializers:
            raise CommandError('Only --all or --serializers must be specified, not together')

        if all:
            for app in apps.get_app_configs():
                # Filter external modules
                if str(settings.BASE_DIR.parent) not in app.path or '.venv' in app.path:
                    continue

                serializers += self._get_app_serializers(app.name)

        for serializer in serializers:
            user_input = serializer.split('.')

            # Only app name
            if len(user_input) == 1:
                app_name = user_input[0]
                serializers_list = self._get_app_serializers(app_name)
            elif len(user_input) == 2:
                app_name, serializer_name = user_input
                serializers_list = _get_serializers_for_module(app_name, serializer_name)
            # Submodule
            else:
                app_name, submodule = serializer.split('.', 1)
                serializers_list = self._get_submodule_serializers(serializer)

            for s in serializers_list:
                    self._generate_ts(s, output, **options)