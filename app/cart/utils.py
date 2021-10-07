from shared_models.models import StoreCourseSection, StoreCertificate, CourseEnrollment, CertificateEnrollment


def get_store_from_product(products):
    product = products.first()
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
