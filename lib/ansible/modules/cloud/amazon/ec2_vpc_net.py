#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['stableinterface'],
                    'supported_by': 'core'}


DOCUMENTATION = '''
---
module: ec2_vpc_net
short_description: Configure AWS virtual private clouds
description:
    - Create or terminate AWS virtual private clouds.  This module has a dependency on python-boto.
version_added: "2.0"
author: Jonathan Davila (@defionscode)
options:
  name:
    description:
      - The name to give your VPC. This is used in combination with the cidr_block parameter to determine if a VPC already exists.
    required: yes
  cidr_block:
    description:
      - The CIDR of the VPC
    required: yes
  tenancy:
    description:
      - Whether to be default or dedicated tenancy. This cannot be changed after the VPC has been created.
    required: false
    default: default
    choices: [ 'default', 'dedicated' ]
  dns_support:
    description:
      - Whether to enable AWS DNS support.
    required: false
    default: yes
    choices: [ 'yes', 'no' ]
  dns_hostnames:
    description:
      - Whether to enable AWS hostname support.
    required: false
    default: yes
    choices: [ 'yes', 'no' ]
  dhcp_opts_id:
    description:
      - the id of the DHCP options to use for this vpc
    default: null
    required: false
  tags:
    description:
      - The tags you want attached to the VPC. This is independent of the name value, note if you pass a 'Name' key it would override the Name of
        the VPC if it's different.
    default: None
    required: false
    aliases: [ 'resource_tags' ]
  state:
    description:
      - The state of the VPC. Either absent or present.
    default: present
    required: false
    choices: [ 'present', 'absent' ]
  multi_ok:
    description:
      - By default the module will not create another VPC if there is another VPC with the same name and CIDR block. Specify this as true if you want
        duplicate VPCs created.
    default: false
    required: false

extends_documentation_fragment:
    - aws
    - ec2
'''

EXAMPLES = '''
# Note: These examples do not set authentication details, see the AWS Guide for details.

# Create a VPC with dedicate tenancy and a couple of tags

- ec2_vpc_net:
    name: Module_dev2
    cidr_block: 10.10.0.0/16
    region: us-east-1
    tags:
      module: ec2_vpc_net
      this: works
    tenancy: dedicated

'''

RETURN = '''
vpc.id:
    description: VPC resource id
    returned: success
    type: string
    sample: vpc-b883b2c4
vpc.cidr_block:
    description: The CIDR of the VPC
    returned: success
    type: string
    sample: "10.0.0.0/16"
vpc.state:
    description: state of the VPC
    returned: success
    type: string
    sample: available
vpc.tags:
    description: tags attached to the VPC, includes name
    returned: success
    type: dict
    sample: {"Name": "My VPC", "env": "staging"}
vpc.classic_link_enabled:
    description: indicates whether ClassicLink is enabled
    returned: success
    type: boolean
    sample: false
vpc.dhcp_options_id:
    description: the id of the DHCP options assocaited with this VPC
    returned: success
    type: string
    sample: dopt-67236184
vpc.instance_tenancy:
    description: indicates whther VPC uses default or dedicated tenancy
    returned: success
    type: string
    sample: default
vpc.is_default:
    description: indicates whether this is the default VPC
    returned: success
    type: boolean
    sample: false
'''

try:
    import boto.vpc
    from boto.exception import BotoServerError, NoAuthHandlerFound
except ImportError:
    pass  # Taken care of by ec2.HAS_BOTO

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.ec2 import (HAS_BOTO, AnsibleAWSError, boto_exception, connect_to_aws,
                                      ec2_argument_spec, get_aws_connection_info)


def vpc_exists(module, vpc, name, cidr_block, multi):
    """Returns None or a vpc object depending on the existence of a VPC. When supplied
    with a CIDR, it will check for matching tags to determine if it is a match
    otherwise it will assume the VPC does not exist and thus return None.
    """
    matched_vpc = None

    try:
        matching_vpcs = vpc.get_all_vpcs(filters={'tag:Name': name, 'cidr-block': cidr_block})
    except Exception as e:
        e_msg = boto_exception(e)
        module.fail_json(msg=e_msg)

    if multi:
        return None
    elif len(matching_vpcs) == 1:
        matched_vpc = matching_vpcs[0]
    elif len(matching_vpcs) > 1:
        module.fail_json(msg='Currently there are %d VPCs that have the same name and '
                             'CIDR block you specified. If you would like to create '
                             'the VPC anyway please pass True to the multi_ok param.' % len(matching_vpcs))

    return matched_vpc


def update_vpc_tags(vpc, module, vpc_obj, tags, name):

    if tags is None:
        tags = dict()

    tags.update({'Name': name})
    try:
        current_tags = dict((t.name, t.value) for t in vpc.get_all_tags(filters={'resource-id': vpc_obj.id}))
        if tags != current_tags:
            if not module.check_mode:
                vpc.create_tags(vpc_obj.id, tags)
            return True
        else:
            return False
    except Exception as e:
        e_msg = boto_exception(e)
        module.fail_json(msg=e_msg)


def update_dhcp_opts(connection, module, vpc_obj, dhcp_id):

    if vpc_obj.dhcp_options_id != dhcp_id:
        if not module.check_mode:
            connection.associate_dhcp_options(dhcp_id, vpc_obj.id)
        return True
    else:
        return False


def get_vpc_values(vpc_obj):

    if vpc_obj is not None:
        vpc_values = vpc_obj.__dict__
        if "region" in vpc_values:
            vpc_values.pop("region")
        if "item" in vpc_values:
            vpc_values.pop("item")
        if "connection" in vpc_values:
            vpc_values.pop("connection")
        return vpc_values
    else:
        return None


def main():
    argument_spec = ec2_argument_spec()
    argument_spec.update(dict(
        name=dict(type='str', default=None, required=True),
        cidr_block=dict(type='str', default=None, required=True),
        tenancy=dict(choices=['default', 'dedicated'], default='default'),
        dns_support=dict(type='bool', default=True),
        dns_hostnames=dict(type='bool', default=True),
        dhcp_opts_id=dict(type='str', default=None, required=False),
        tags=dict(type='dict', required=False, default=None, aliases=['resource_tags']),
        state=dict(choices=['present', 'absent'], default='present'),
        multi_ok=dict(type='bool', default=False)
    )
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )

    if not HAS_BOTO:
        module.fail_json(msg='boto is required for this module')

    name = module.params.get('name')
    cidr_block = module.params.get('cidr_block')
    tenancy = module.params.get('tenancy')
    dns_support = module.params.get('dns_support')
    dns_hostnames = module.params.get('dns_hostnames')
    dhcp_id = module.params.get('dhcp_opts_id')
    tags = module.params.get('tags')
    state = module.params.get('state')
    multi = module.params.get('multi_ok')

    changed = False

    region, ec2_url, aws_connect_params = get_aws_connection_info(module)

    if region:
        try:
            connection = connect_to_aws(boto.vpc, region, **aws_connect_params)
        except (NoAuthHandlerFound, AnsibleAWSError) as e:
            module.fail_json(msg=str(e))
    else:
        module.fail_json(msg="region must be specified")

    if dns_hostnames and not dns_support:
        module.fail_json(msg='In order to enable DNS Hostnames you must also enable DNS support')

    if state == 'present':

        # Check if VPC exists
        vpc_obj = vpc_exists(module, connection, name, cidr_block, multi)

        if vpc_obj is None:
            try:
                changed = True
                if not module.check_mode:
                    vpc_obj = connection.create_vpc(cidr_block, instance_tenancy=tenancy)
                else:
                    module.exit_json(changed=changed)
            except BotoServerError as e:
                module.fail_json(msg=e)

        if dhcp_id is not None:
            try:
                if update_dhcp_opts(connection, module, vpc_obj, dhcp_id):
                    changed = True
            except BotoServerError as e:
                module.fail_json(msg=e)

        if tags is not None or name is not None:
            try:
                if update_vpc_tags(connection, module, vpc_obj, tags, name):
                    changed = True
            except BotoServerError as e:
                module.fail_json(msg=e)

        # Note: Boto currently doesn't currently provide an interface to ec2-describe-vpc-attribute
        # which is needed in order to detect the current status of DNS options. For now we just update
        # the attribute each time and is not used as a changed-factor.
        try:
            if not module.check_mode:
                connection.modify_vpc_attribute(vpc_obj.id, enable_dns_support=dns_support)
                connection.modify_vpc_attribute(vpc_obj.id, enable_dns_hostnames=dns_hostnames)
        except BotoServerError as e:
            e_msg = boto_exception(e)
            module.fail_json(msg=e_msg)

        if not module.check_mode:
            # get the vpc obj again in case it has changed
            try:
                vpc_obj = connection.get_all_vpcs(vpc_obj.id)[0]
            except BotoServerError as e:
                e_msg = boto_exception(e)
                module.fail_json(msg=e_msg)

        module.exit_json(changed=changed, vpc=get_vpc_values(vpc_obj))

    elif state == 'absent':

        # Check if VPC exists
        vpc_obj = vpc_exists(module, connection, name, cidr_block, multi)

        if vpc_obj is not None:
            try:
                if not module.check_mode:
                    connection.delete_vpc(vpc_obj.id)
                vpc_obj = None
                changed = True
            except BotoServerError as e:
                e_msg = boto_exception(e)
                module.fail_json(msg="%s. You may want to use the ec2_vpc_subnet, ec2_vpc_igw, "
                                 "and/or ec2_vpc_route_table modules to ensure the other components are absent." % e_msg)

        module.exit_json(changed=changed, vpc=get_vpc_values(vpc_obj))


if __name__ == '__main__':
    main()
