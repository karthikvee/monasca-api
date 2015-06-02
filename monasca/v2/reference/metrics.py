# Copyright 2014 Hewlett-Packard
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import falcon
from oslo.config import cfg

from monasca.api import monasca_api_v2
from monasca.common.messaging import exceptions as message_queue_exceptions
from monasca.common.messaging.message_formats import metrics_transform_factory
from monasca.common import resource_api
from monasca.openstack.common import log
from monasca.v2.reference import helpers
from monasca.v2.reference import resource


LOG = log.getLogger(__name__)


class Metrics(monasca_api_v2.V2API):
    def __init__(self, global_conf):

        try:

            super(Metrics, self).__init__(global_conf)

            self._region = cfg.CONF.region
            self._default_authorized_roles = (
                cfg.CONF.security.default_authorized_roles)
            self._delegate_authorized_roles = (
                cfg.CONF.security.delegate_authorized_roles)
            self._post_metrics_authorized_roles = (
                cfg.CONF.security.default_authorized_roles +
                cfg.CONF.security.agent_authorized_roles)
            self._metrics_transform = (
                metrics_transform_factory.create_metrics_transform())
            self._message_queue = (
                resource_api.init_driver('monasca.messaging',
                                         cfg.CONF.messaging.driver,
                                         ['metrics']))
            self._metrics_repo = resource_api.init_driver(
                'monasca.repositories', cfg.CONF.repositories.metrics_driver)

        except Exception as ex:
            LOG.exception(ex)
            raise falcon.HTTPInternalServerError('Service unavailable',
                                                 ex.message)

    def _validate_metrics(self, metrics):

        try:
            if isinstance(metrics, list):
                for metric in metrics:
                    self._validate_single_metric(metric)
            else:
                self._validate_single_metric(metrics)
        except Exception as ex:
            LOG.debug(ex)
            raise falcon.HTTPBadRequest('Bad request', ex.message)

    def _validate_single_metric(self, metric):
        assert isinstance(metric['name'], (str, unicode))
        assert len(metric['name']) <= 64
        assert isinstance(metric['timestamp'], (int, float))
        assert isinstance(metric['value'], (int, long, float, complex))
        if "dimensions" in metric:
            for d in metric['dimensions']:
                assert isinstance(d, (str, unicode))
                assert len(d) <= 255
                assert isinstance(metric['dimensions'][d], (str, unicode))
                assert len(metric['dimensions'][d]) <= 255

    def _send_metrics(self, metrics):

        try:
            self._message_queue.send_message_batch(metrics)
        except message_queue_exceptions.MessageQueueException as ex:
            LOG.exception(ex)
            raise falcon.HTTPServiceUnavailable('Service unavailable',
                                                ex.message, 60)

    @resource.resource_try_catch_block
    def _list_metrics(self, tenant_id, name, dimensions, req_uri, offset,
                      limit):

        result = self._metrics_repo.list_metrics(tenant_id,
                                                 self._region,
                                                 name,
                                                 dimensions, offset, limit)

        return helpers.paginate(result, req_uri, limit)

    @resource.resource_try_catch_block
    def _list_metric_names(self, tenant_id, dimensions, req_uri, offset,
                           limit):

        result = self._metrics_repo.list_metric_names(tenant_id,
                                                      self._region,
                                                      dimensions,
                                                      offset, limit)

        return helpers.paginate(result, req_uri, limit)

    @resource.resource_try_catch_block
    def _measurement_list(self, tenant_id, name, dimensions, start_timestamp,
                          end_timestamp, req_uri, offset,
                          limit, merge_metrics_flag):

        result = self._metrics_repo.measurement_list(tenant_id,
                                                     self._region,
                                                     name,
                                                     dimensions,
                                                     start_timestamp,
                                                     end_timestamp,
                                                     offset,
                                                     limit,
                                                     merge_metrics_flag)

        return helpers.paginate_measurement(result, req_uri, limit)

    @resource.resource_try_catch_block
    def _metric_statistics(self, tenant_id, name, dimensions, start_timestamp,
                           end_timestamp, statistics, period, req_uri,
                           offset, limit, merge_metrics_flag):

        result = self._metrics_repo.metrics_statistics(tenant_id,
                                                       self._region,
                                                       name,
                                                       dimensions,
                                                       start_timestamp,
                                                       end_timestamp,
                                                       statistics, period,
                                                       offset,
                                                       limit,
                                                       merge_metrics_flag)

        return helpers.paginate_statistics(result, req_uri, limit)

    @resource_api.Restify('/v2.0/metrics/', method='post')
    def do_post_metrics(self, req, res):
        helpers.validate_json_content_type(req)
        helpers.validate_authorization(req,
                                       self._post_metrics_authorized_roles)
        metrics = helpers.read_http_resource(req)
        self._validate_metrics(metrics)
        tenant_id = (
            helpers.get_x_tenant_or_tenant_id(req,
                                              self._delegate_authorized_roles))
        transformed_metrics = self._metrics_transform(metrics, tenant_id,
                                                      self._region)
        self._send_metrics(transformed_metrics)
        res.status = falcon.HTTP_204

    @resource_api.Restify('/v2.0/metrics/', method='get')
    def do_get_metrics(self, req, res):
        helpers.validate_authorization(req, self._default_authorized_roles)
        tenant_id = helpers.get_tenant_id(req)
        name = helpers.get_query_name(req)
        helpers.validate_query_name(name)
        dimensions = helpers.get_query_dimensions(req)
        helpers.validate_query_dimensions(dimensions)
        offset = helpers.get_query_param(req, 'offset')
        limit = helpers.get_limit(req)
        result = self._list_metrics(tenant_id, name, dimensions,
                                    req.uri, offset, limit)
        res.body = helpers.dumpit_utf8(result)
        res.status = falcon.HTTP_200

    @resource_api.Restify('/v2.0/metrics/measurements', method='get')
    def do_get_measurements(self, req, res):
        helpers.validate_authorization(req, self._default_authorized_roles)
        tenant_id = helpers.get_tenant_id(req)
        name = helpers.get_query_name(req, True)
        helpers.validate_query_name(name)
        dimensions = helpers.get_query_dimensions(req)
        helpers.validate_query_dimensions(dimensions)
        start_timestamp = helpers.get_query_starttime_timestamp(req)
        end_timestamp = helpers.get_query_endtime_timestamp(req, False)
        offset = helpers.get_query_param(req, 'offset')
        limit = helpers.get_limit(req)
        merge_metrics_flag = helpers.get_query_param(req, 'merge_metrics',
                                                     False,
                                                     False)
        merge_metrics_flag = (
            self._get_boolean_merge_metrics_flag(merge_metrics_flag))

        result = self._measurement_list(tenant_id, name, dimensions,
                                        start_timestamp, end_timestamp,
                                        req.uri, offset,
                                        limit, merge_metrics_flag)

        res.body = helpers.dumpit_utf8(result)
        res.status = falcon.HTTP_200

    @resource_api.Restify('/v2.0/metrics/names', method='get')
    def do_get_metric_names(self, req, res):
        helpers.validate_authorization(req, self._default_authorized_roles)
        tenant_id = helpers.get_tenant_id(req)
        dimensions = helpers.get_query_dimensions(req)
        helpers.validate_query_dimensions(dimensions)
        offset = helpers.get_query_param(req, 'offset')
        limit = helpers.get_limit(req)
        result = self._list_metric_names(tenant_id, dimensions,
                                         req.uri, offset, limit)
        res.body = helpers.dumpit_utf8(result)
        res.status = falcon.HTTP_200

    @resource_api.Restify('/v2.0/metrics/statistics', method='get')
    def do_get_statistics(self, req, res):
        helpers.validate_authorization(req, self._default_authorized_roles)
        tenant_id = helpers.get_tenant_id(req)
        name = helpers.get_query_name(req, True)
        helpers.validate_query_name(name)
        dimensions = helpers.get_query_dimensions(req)
        helpers.validate_query_dimensions(dimensions)
        start_timestamp = helpers.get_query_starttime_timestamp(req)
        end_timestamp = helpers.get_query_endtime_timestamp(req, False)
        statistics = helpers.get_query_statistics(req)
        period = helpers.get_query_period(req)
        offset = helpers.get_query_param(req, 'offset')
        limit = helpers.get_limit(req)
        merge_metrics_flag = helpers.get_query_param(req, 'merge_metrics',
                                                     False,
                                                     False)

        merge_metrics_flag = (
            self._get_boolean_merge_metrics_flag(merge_metrics_flag))

        result = self._metric_statistics(tenant_id, name, dimensions,
                                         start_timestamp, end_timestamp,
                                         statistics, period, req.uri,
                                         offset, limit, merge_metrics_flag)

        res.body = helpers.dumpit_utf8(result)
        res.status = falcon.HTTP_200

    def _get_boolean_merge_metrics_flag(self, merge_metrics_flag_str):

        if merge_metrics_flag_str is not False:
            return helpers.str_2_bool(merge_metrics_flag_str)
        else:
            return False
