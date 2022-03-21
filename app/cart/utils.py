from django.http import Http404
from models.course.course import Course as CourseModel
from models.courseprovider.course_provider import CourseProvider as CourseProviderModel
from shared_models.models import Course, StoreCourseSection, CourseSharingContract
from django_scopes import scopes_disabled
from urllib.parse import parse_qs

def get_product_ids(store, search_params):
    parsed_params = parse_qs(search_params)

    provider_codes = [item[0] for item in CourseSharingContract.objects.filter(store=store).values_list('course_provider__code')]

    product_ids = []
    if 'section' in parsed_params:
        external_ids = parsed_params.get('section', [])
        for item in external_ids:
            for section in item.split(','):
                course_external_id, section_external_id = section.split('__')

                course_provider_models = CourseProviderModel.objects.filter(
                    code__in=provider_codes
                )

                # as there are multiple course providers, the following query may return multiple courses. what should happen should it does is not determined yet.
                try:
                    course_model = CourseModel.objects.get(
                        provider__in=course_provider_models,
                        external_id=course_external_id
                    )
                except CourseModel.DoesNotExist:
                    continue
                except CourseModel.MultipleObjectsReturned:
                    raise NotImplementedError

                with scopes_disabled():
                    try:
                        # this query also may return multiple objects
                        course = Course.objects.get(
                            content_db_reference=str(course_model.id),
                            course_provider__code__in=provider_codes
                        )
                    except Course.DoesNotExist:
                        continue
                    except Course.MultipleObjectsReturned:
                        raise NotImplementedError

                    # get the section name. section name and section code are same. but external_id is different.
                    # so make one more loop and more db transaction to get the name. otherwise won't work.
                    section_name = ''
                    for section_model in course_model.sections:
                        if section_model.external_id == section_external_id:
                            section_name = section_model.code
                            break

                    try:
                        store_course_section = StoreCourseSection.objects.get(
                            # since external_id in SectionModel is the same as code in SectionModel and that in turn is the same as name in Section
                            section__name=section_name,
                            store_course__course=course,
                            store_course__store=store,
                        )
                    except StoreCourseSection.DoesNotExist:
                        continue
                    else:
                        try:
                            product_ids.append(str(store_course_section.product.id))
                        except AttributeError:
                            continue
    return product_ids
