// SPDX-License-Identifier: GPL-2.0-only
/*
 * lenovo_fanboost - fan speed request/readback for ThinkBook 14 G7 ARP (21MV)
 *
 * Mechanism only. Requests a fan speed through the firmware WMI method
 * \_SB.WMI5.WMLA(0, 0x12, {SIDS=0x04030001, SVAL=rpm}); rpm 0 returns the fan
 * to automatic EC control. Policy lives in user space (lenovo-fanboost).
 * The GUID bound by lenovo_wmi_other is not touched; the method is called
 * directly through ACPI.
 */
#include <linux/acpi.h>
#include <linux/dmi.h>
#include <linux/err.h>
#include <linux/hwmon.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/pm.h>
#include <linux/sysfs.h>
#include <linux/unaligned.h>

#define FB_METHOD	"\\_SB.WMI5.WMLA"
#define FB_SET_CMD	0x12
#define FB_SID_FAN1	0x04030001
#define FB_MAX_RPM	4000
#define FB_EC_FAN_REG	0x95

static unsigned int rpm_per_unit;
module_param(rpm_per_unit, uint, 0444);
MODULE_PARM_DESC(rpm_per_unit, "RPM per EC 0x95 unit; fan1_input exists only if non-zero (unverified, ~50)");

struct fb_data {
	acpi_handle handle;
	struct mutex lock;	/* serializes requests and target */
	long target;
};

static struct platform_device *fb_pdev;

static int fb_request(struct fb_data *d, u32 rpm)
{
	union acpi_object args[3];
	struct acpi_object_list list = { .count = 3, .pointer = args };
	u8 buf[8];
	acpi_status st;

	put_unaligned_le32(FB_SID_FAN1, buf);
	put_unaligned_le32(rpm, buf + 4);
	args[0].type = ACPI_TYPE_INTEGER;
	args[0].integer.value = 0;
	args[1].type = ACPI_TYPE_INTEGER;
	args[1].integer.value = FB_SET_CMD;
	args[2].type = ACPI_TYPE_BUFFER;
	args[2].buffer.length = sizeof(buf);
	args[2].buffer.pointer = buf;

	st = acpi_evaluate_object(d->handle, NULL, &list, NULL);
	return ACPI_FAILURE(st) ? -EIO : 0;
}

static ssize_t fan1_raw_show(struct device *dev, struct device_attribute *attr,
			     char *buf)
{
	u8 v;
	int ret = ec_read(FB_EC_FAN_REG, &v);

	if (ret)
		return ret;
	return sysfs_emit(buf, "%u\n", v);
}
static DEVICE_ATTR_RO(fan1_raw);

static struct attribute *fb_attrs[] = {
	&dev_attr_fan1_raw.attr,
	NULL
};
ATTRIBUTE_GROUPS(fb);

static umode_t fb_is_visible(const void *data, enum hwmon_sensor_types type,
			     u32 attr, int channel)
{
	if (type != hwmon_fan || channel)
		return 0;
	switch (attr) {
	case hwmon_fan_input:
		return rpm_per_unit ? 0444 : 0;
	case hwmon_fan_target:
		return 0644;
	}
	return 0;
}

static int fb_read(struct device *dev, enum hwmon_sensor_types type, u32 attr,
		   int channel, long *val)
{
	struct fb_data *d = dev_get_drvdata(dev);
	u8 v;
	int ret;

	switch (attr) {
	case hwmon_fan_input:
		ret = ec_read(FB_EC_FAN_REG, &v);
		if (ret)
			return ret;
		*val = (long)v * rpm_per_unit;
		return 0;
	case hwmon_fan_target:
		mutex_lock(&d->lock);
		*val = d->target;
		mutex_unlock(&d->lock);
		return 0;
	}
	return -EOPNOTSUPP;
}

static int fb_write(struct device *dev, enum hwmon_sensor_types type, u32 attr,
		    int channel, long val)
{
	struct fb_data *d = dev_get_drvdata(dev);
	int ret;

	if (attr != hwmon_fan_target)
		return -EOPNOTSUPP;

	val = clamp_val(val, 0, FB_MAX_RPM);
	mutex_lock(&d->lock);
	ret = fb_request(d, val);
	if (!ret)
		d->target = val;
	mutex_unlock(&d->lock);
	return ret;
}

static const struct hwmon_ops fb_ops = {
	.is_visible = fb_is_visible,
	.read = fb_read,
	.write = fb_write,
};

static const struct hwmon_channel_info * const fb_info[] = {
	HWMON_CHANNEL_INFO(fan, HWMON_F_INPUT | HWMON_F_TARGET),
	NULL
};

static const struct hwmon_chip_info fb_chip = {
	.ops = &fb_ops,
	.info = fb_info,
};

static void fb_release(struct fb_data *d)
{
	mutex_lock(&d->lock);
	if (!fb_request(d, 0))
		d->target = 0;
	mutex_unlock(&d->lock);
}

static int fb_probe(struct platform_device *pdev)
{
	struct device *hwdev;
	struct fb_data *d;
	acpi_status st;

	d = devm_kzalloc(&pdev->dev, sizeof(*d), GFP_KERNEL);
	if (!d)
		return -ENOMEM;
	st = acpi_get_handle(NULL, FB_METHOD, &d->handle);
	if (ACPI_FAILURE(st))
		return -ENODEV;
	mutex_init(&d->lock);
	platform_set_drvdata(pdev, d);

	fb_release(d);	/* known state: automatic */
	hwdev = devm_hwmon_device_register_with_info(&pdev->dev,
						     "lenovo_fanboost", d,
						     &fb_chip, fb_groups);
	return PTR_ERR_OR_ZERO(hwdev);
}

static void fb_remove(struct platform_device *pdev)
{
	fb_release(platform_get_drvdata(pdev));
}

static void fb_shutdown(struct platform_device *pdev)
{
	fb_release(platform_get_drvdata(pdev));
}

static int fb_suspend(struct device *dev)
{
	fb_release(dev_get_drvdata(dev));
	return 0;
}
static DEFINE_SIMPLE_DEV_PM_OPS(fb_pm, fb_suspend, NULL);

static struct platform_driver fb_driver = {
	.driver = {
		.name = "lenovo_fanboost",
		.pm = pm_sleep_ptr(&fb_pm),
	},
	.probe = fb_probe,
	.remove = fb_remove,
	.shutdown = fb_shutdown,
};

static const struct dmi_system_id fb_dmi[] = {
	{
		.ident = "ThinkBook 14 G7 ARP",
		.matches = {
			DMI_MATCH(DMI_SYS_VENDOR, "LENOVO"),
			DMI_MATCH(DMI_PRODUCT_NAME, "21MV"),
		},
	},
	{ }
};
MODULE_DEVICE_TABLE(dmi, fb_dmi);

static int __init fb_init(void)
{
	acpi_handle h;
	int ret;

	if (!dmi_check_system(fb_dmi))
		return -ENODEV;
	if (ACPI_FAILURE(acpi_get_handle(NULL, FB_METHOD, &h)))
		return -ENODEV;

	ret = platform_driver_register(&fb_driver);
	if (ret)
		return ret;
	fb_pdev = platform_device_register_simple("lenovo_fanboost", PLATFORM_DEVID_NONE,
						  NULL, 0);
	if (IS_ERR(fb_pdev)) {
		platform_driver_unregister(&fb_driver);
		return PTR_ERR(fb_pdev);
	}
	if (!device_is_bound(&fb_pdev->dev)) {	/* probe failed */
		platform_device_unregister(fb_pdev);
		platform_driver_unregister(&fb_driver);
		return -ENODEV;
	}
	return 0;
}

static void __exit fb_exit(void)
{
	platform_device_unregister(fb_pdev);
	platform_driver_unregister(&fb_driver);
}

module_init(fb_init);
module_exit(fb_exit);

MODULE_AUTHOR("lenovo-fanboost contributors");
MODULE_DESCRIPTION("Fan speed request for Lenovo ThinkBook 14 G7 ARP (21MV)");
MODULE_LICENSE("GPL");
