# from mongoengine import get_db
# from django.utils import timezone
# from cart.amqp_connector import AMQPConnection


# def save_failed_messages(data):
#     print('Adding tasks payload to mongodb')
#     db = get_db()
#     coll = db.get_collection('mq_tasks')
#     coll.insert_one({'payload': data, 'datetime': timezone.now()})
#     print('Done')


# def generic_task_enqueue(
#     routing_key,
#     refund_id=None,
#     cart_id=None,
#     payment_id=None,
#     store_payment_gateway_id=None,
#     external_id=None,
#     profile_id=None,
#     course_enrollment_id=None,
#     product_id=None,
#     store_course_section_id=None,
#     hubspot_token=None,
#     import_task_id=None,
#     store_id=None,
#     enrollment_login_link=True
# ):
#     payload = {
#         'routing_key': routing_key,
#         'refund_id': refund_id,
#         'cart_id': cart_id,
#         'payment_id': payment_id,
#         'store_payment_gateway_id': store_payment_gateway_id,
#         'external_id': external_id,
#         'profile_id': profile_id,
#         'course_enrollment_id': course_enrollment_id,
#         'product_id': product_id,
#         'store_course_section_id': store_course_section_id,
#         'hubspot_token': hubspot_token,
#         'import_task_id': import_task_id,
#         'store_id': store_id,
#         'enrollment_login_link': enrollment_login_link
#     }

#     connection = AMQPConnection()
#     try:
#         connection.basic_publish(routing_key, payload)
#     except Exception as e:
#         save_failed_messages(payload)
#         print('Adding tasks failed: ', str(e))
