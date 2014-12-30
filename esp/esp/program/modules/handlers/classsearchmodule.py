import json

from django.db.models.query import Q

from esp.program.modules.base import ProgramModuleObj, main_call, needs_admin
from esp.program.models.class_ import ClassSubject, STATUS_CHOICES_DICT
from esp.program.models.flags import ClassFlagType
from esp.utils.query_builder import QueryBuilder, SearchFilter
from esp.utils.query_builder import SelectInput, TrivialInput
from esp.utils.query_builder import OptionalInput, DatetimeInput
from esp.web.util import render_to_response

# TODO: this won't work right without class flags enabled


class ClassSearchModule(ProgramModuleObj):
    """Search for classes matching certain criteria."""
    @classmethod
    def module_properties(cls):
        return {
            "admin_title": "Class Search",
            "link_title": "Search for classes",
            "module_type": "manage",
            "seq": 10,
        }

    class Meta:
        proxy = True

    def query_builder(self):
        flag_filter = SearchFilter(
            name='flag',
            title='the flag',
            inputs=[
                SelectInput(
                    field_name='flags__flag_type',
                    options={
                        ft.id: ft.name for ft in
                        ClassFlagType.get_flag_types(program=self.program)},
                    english_name='type',
                ),
                OptionalInput(
                    name='(show created time)',
                    inner=DatetimeInput(
                        field_name='flags__modified_time',
                        english_name='modified',
                    ),
                ),
                OptionalInput(
                    name='(show created time)',
                    inner=DatetimeInput(
                        field_name='flags__created_time',
                        english_name='created',
                    ),
                ),

            ])
        status_filter = SearchFilter(
            name='status',
            title='the status',
            inputs=[
                SelectInput(
                    field_name='status',
                    options=STATUS_CHOICES_DICT,
                ),
            ])
        categories = list(self.program.class_categories.all())
        if self.program.open_class_registration:
            categories.append(self.program.open_class_category)
        category_filter = SearchFilter(
            name='category',
            title='the category',
            inputs=[
                SelectInput(
                    field_name='category',
                    options={cat.id: cat.category for cat in categories},
                ),
            ])
        all_scheduled_filter = SearchFilter(
            name="all_scheduled",
            title="all sections scheduled",
            # Exclude classes with sections with null meeting times
            inverted=True,
            inputs=[TrivialInput(Q(sections__meeting_times__isnull=True))],
        )
        some_scheduled_filter = SearchFilter(
            name="some_scheduled",
            title="some sections scheduled",
            # Get classes with sections with non-null meeting times
            inputs=[TrivialInput(Q(sections__meeting_times__isnull=False))],
        )

        return QueryBuilder(
            base=ClassSubject.objects.filter(parent_program=self.program),
            english_name="classes",
            filters=[
                flag_filter,
                status_filter,
                category_filter,
                all_scheduled_filter,
                some_scheduled_filter,
            ])

    @main_call
    @needs_admin
    def classsearch(self, request, tl, one, two, module, extra, prog):
        data = request.GET.get('query')
        query_builder = self.query_builder()
        if data is None:
            # Display a blank query builder
            context = {
                'query_builder': query_builder.render(),
                'program': self.program,
            }
            return render_to_response(self.baseDir()+'query_builder.html',
                                      request, context)
        else:
            decoded = json.loads(data)
            queryset = query_builder.as_queryset(decoded)
            queryset = queryset.distinct().order_by('id').prefetch_related(
                'flags', 'flags__flag_type', 'teachers', 'category',
                'sections')
            english = query_builder.as_english(decoded)
            context = {
                'queryset': queryset,
                'english': english,
                'program': self.program,
            }
            return render_to_response(self.baseDir()+'search_results.html',
                                      request, context)
