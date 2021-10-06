from shared_models.models import StoreCourseSection, StoreCertificate, CourseEnrollment, CertificateEnrollment


def get_store_from_product(product):
    try:
        return product.store_course_section.store_course.store
    except StoreCourseSection.DoesNotExist:
        pass

    try:
        return product.store_certificate.store
    except StoreCertificate.DoesNotExist:
        pass

    # raise some kind of exception
    return None


def is_already_enrolled(product, profile):
    try:
        store_course_section = StoreCourseSection.objects.get(product=product)
    except StoreCourseSection.DoesNotExist:
        pass  # being silent
    else:
        if CourseEnrollment.objects.filter(
                profile=profile,
                store=store_course_section.store_course.store,
                course=store_course_section.store_course.course,
                section=store_course_section.section,
                status=CourseEnrollment.STATUS_SUCCESS).exists():

            return True

    try:
        store_certificate = StoreCertificate.objects.get(product=product)
    except StoreCertificate.DoesNotExist:
        pass
    else:
        if CertificateEnrollment.objects.filter(
                profile=profile,
                certificate=store_certificate.certificate,
                store=store_certificate.store,
                status=CertificateEnrollment.STATUS_SUCCESS).exists():
            return True
    return False


def get_formatted_data_and_price(product):
    product_data = {}

    try:
        store_certificate = StoreCertificate.objects.get(product=product)
    except StoreCertificate.DoesNotExist:
        pass
    else:
        product_data = {
            'id': str(store_certificate.certificate.id),
            'title': store_certificate.certificate.title,
            'slug': store_certificate.certificate.slug,
            'image_uri': store_certificate.certificate.certificate_image_uri.url if store_certificate.certificate.certificate_image_uri else store_certificate.certificate.external_image_url,
            'external_image_url': store_certificate.certificate.external_image_url,
            'provider': {
                'id': store_certificate.certificate.course_provider.content_db_reference,
                'code': store_certificate.certificate.course_provider.code
            },
            'price': product.fee,
            'product_type': 'certificate'
        }

    try:
        store_course_section = StoreCourseSection.objects.get(product=product)
    except StoreCourseSection.DoesNotExist:
        pass
    else:
        product_data = {
            'id': store_course_section.store_course.course.id,
            'title': store_course_section.store_course.course.title,
            'slug': store_course_section.store_course.course.slug,
            'image_uri': store_course_section.store_course.course.course_image_uri.url if store_course_section.store_course.course.course_image_uri else store_course_section.store_course.course.external_image_url,
            'external_image_url': store_course_section.store_course.course.external_image_url,
            'provider': {
                'id': store_course_section.store_course.course.course_provider.content_db_reference,
                'code': store_course_section.store_course.course.course_provider.code
            },
            'product_type': 'store_course_section',
            'section': {
                'start_date': store_course_section.section.start_date,
                'end_date': store_course_section.section.end_date,
                'execution_site': store_course_section.section.execution_site,
                'execution_mode': store_course_section.section.execution_mode
            },
            'price': product.fee,
            'questionnaire': [
                {
                    'type': 'checkbox',
                    'field': 'have_relevant_certificate',
                    'label': 'Do you have a relevant certificate?'
                },
                {
                    'type': 'text',
                    'field': 'certificate_number',
                    'label': 'Enter the certificate number'
                },
                {
                    'type': 'date',
                    'field': 'certificate_expiry_date',
                    'label': 'Certificate expiry date'
                }
            ]
        }

    return (product.fee, product_data)
